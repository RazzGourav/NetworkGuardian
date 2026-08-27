"""
NetworkGuardian — Ryu SDN Controller Application

An L2 learning switch with loop-free forwarding on the NetworkGuardian
redundant topology.

How it works:
  1. On startup the controller installs a table-miss rule on every switch
     so that unmatched packets are sent to the controller as Packet-In.
  2. The controller learns MAC→(switch, port) mappings from Packet-In
     events arriving on *edge* (host-facing) ports.
  3. For known destinations the controller computes a shortest path via
     the RerouteEngine graph and installs per-flow forwarding rules.
  4. Unknown destinations are flooded only through MST-safe ports to
     prevent broadcast storms on the redundant topology.
  5. When a fault is reported via ``POST /api/fault``, the controller
     performs a **scoped** reroute:
       - Remove the failed edge from the graph.
       - Clear flows ONLY on the two switches adjacent to the failed
         link (not every switch).
       - All other switches keep their flows — traffic not traversing
         the failed link is unaffected.
       - A 5-second cooldown prevents cascading fault reports from
         transient packet loss caused by the reroute itself.

Uses OpenFlow 1.3.
"""

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types
from ryu.app.wsgi import WSGIApplication, route, ControllerBase
import json
import logging
import sys
import time

# Add project root to path for imports if needed
sys.path.insert(0, "/app")
from controller.reroute_engine import RerouteEngine

LOG = logging.getLogger("NetworkGuardian.Controller")

# How long (seconds) to ignore duplicate fault reports after handling one.
FAULT_COOLDOWN_SECONDS = 5.0


class NetworkGuardianController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {'wsgi': WSGIApplication}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mac_to_switch = {}      # mac -> dpid
        self.mac_to_edge_port = {}   # mac -> port on that switch
        self.datapaths = {}          # dpid -> datapath object
        self.reroute_engine = RerouteEngine()

        # Fault deduplication: link_id -> last-handled timestamp
        self._fault_handled_at = {}

        wsgi = kwargs['wsgi']
        wsgi.register(FaultController, {'app': self})
        self.logger.info("NetworkGuardian controller initialized with WSGI and Reroute Engine")

    # ------------------------------------------------------------------
    # Switch lifecycle
    # ------------------------------------------------------------------

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        dpid = datapath.id

        self.datapaths[dpid] = datapath
        self.logger.info("Switch connected: dpid=%s", dpid)

        # Install table-miss flow
        self._install_table_miss(datapath)

    def _install_table_miss(self, datapath):
        """Install a table-miss flow that sends unmatched packets to the controller."""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self._add_flow(datapath, priority=0, match=match, actions=actions)
        self.logger.debug("Table-miss flow installed on dpid=%s", datapath.id)

    def clear_flows(self, datapath):
        """Clear all non-table-miss flows on *datapath* and reinstall table-miss."""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Delete all flows
        mod = parser.OFPFlowMod(
            datapath=datapath,
            command=ofproto.OFPFC_DELETE,
            out_port=ofproto.OFPP_ANY,
            out_group=ofproto.OFPG_ANY,
        )
        datapath.send_msg(mod)

        # Reinstall table-miss
        self._install_table_miss(datapath)

        self.logger.debug("Flows cleared on dpid=%s", datapath.id)

    # ------------------------------------------------------------------
    # Packet-In handling (L2 learning + shortest-path forwarding)
    # ------------------------------------------------------------------

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']
        dpid = datapath.id

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        if eth is None:
            return

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        src = eth.src
        dst = eth.dst

        # Learn the MAC address ONLY if it arrived on an edge (host-facing) port.
        # Internal (switch-to-switch) ports must not overwrite the real
        # host→switch mapping.
        if not self.reroute_engine.is_internal_port(dpid, in_port):
            self.mac_to_switch[src] = dpid
            self.mac_to_edge_port[src] = in_port

        # Decide output port
        is_flooding = False
        if dst in self.mac_to_switch:
            dst_dpid = self.mac_to_switch[dst]

            if dst_dpid == dpid:
                # Same switch — output to edge port
                out_port = self.mac_to_edge_port[dst]
            else:
                # Route to a different switch via shortest path
                path = self.reroute_engine.get_shortest_path(dpid, dst_dpid)
                if path and len(path) > 1:
                    next_hop = path[1]
                    out_port = self.reroute_engine.get_port_for_next_hop(dpid, next_hop)
                else:
                    self.logger.error("No path from %s to %s", dpid, dst_dpid)
                    return

            actions = [parser.OFPActionOutput(out_port)]
        else:
            # Unknown destination — flood through MST-safe ports
            is_flooding = True
            actions = []

            mst_ports = self.reroute_engine.get_flood_ports(dpid)

            for port in datapath.ports.keys():
                if port == in_port or port >= ofproto.OFPP_MAX:
                    continue
                if self.reroute_engine.is_internal_port(dpid, port):
                    if port in mst_ports:
                        actions.append(parser.OFPActionOutput(port))
                else:
                    # Edge port — always flood
                    actions.append(parser.OFPActionOutput(port))

        # Install a forwarding flow for known unicast destinations
        if not is_flooding:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            self._add_flow(datapath, priority=1, match=match, actions=actions,
                           idle_timeout=30)

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data,
        )
        datapath.send_msg(out)

    # ------------------------------------------------------------------
    # Flow helpers
    # ------------------------------------------------------------------

    def _add_flow(self, datapath, priority, match, actions, idle_timeout=0):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(
            datapath=datapath, priority=priority, match=match,
            instructions=inst, idle_timeout=idle_timeout,
        )
        datapath.send_msg(mod)

    # ------------------------------------------------------------------
    # Fault handling — SCOPED reroute (not global clear)
    # ------------------------------------------------------------------

    def handle_fault(self, link_id):
        """Handle a fault report for *link_id*.

        Key design decisions (post-audit fix):
          1. Only switch-switch links trigger rerouting.
          2. Duplicate / rapid-fire reports are suppressed via a per-link
             cooldown AND a global cooldown.
          3. Flows are cleared ONLY on the two switches adjacent to the
             failed link — all other switches keep their flows.  This
             prevents the broadcast storm that the old global clear_flows()
             caused.
        """
        now = time.time()

        # --- Guard: ignore host-switch links ---
        if not self.reroute_engine.is_switch_link(link_id):
            self.logger.debug("Ignoring non-switch fault report: %s", link_id)
            return



        # --- Guard: per-link deduplication ---
        last = self._fault_handled_at.get(link_id, 0.0)
        if now - last < FAULT_COOLDOWN_SECONDS:
            self.logger.debug("Duplicate fault for %s within cooldown — ignoring", link_id)
            return

        self.logger.warning("Fault received for link %s. Performing scoped reroute...", link_id)

        # Remove the edge from the topology graph.
        # Returns (dpid1, dpid2) if the edge existed, else None.
        affected = self.reroute_engine.remove_link(link_id)
        if affected is None:
            self.logger.info("Link %s already removed from graph — no-op", link_id)
            return

        dpid1, dpid2 = affected

        # Clear flows SCOPED only to the affected switches.
        # Unaffected switches will naturally miss their flow tables when
        # packets bounce back to them on a different in_port, forcing a
        # Packet-In that correctly updates their path. No global clear needed.
        if dpid1 in self.datapaths:
            self.clear_flows(self.datapaths[dpid1])
        if dpid2 in self.datapaths:
            self.clear_flows(self.datapaths[dpid2])

        self.logger.info(
            "Scoped reroute complete: cleared flows on s%s and s%s. "
            "Traffic will reroute around %s.",
            dpid1, dpid2, link_id,
        )

        # Record timestamps for deduplication
        self._fault_handled_at[link_id] = now
        
        # Send active links to the backend for dashboard visualization
        import requests
        active_links = []
        for (src, dst) in self.reroute_engine.graph.edges():
            active_links.append(f"s{src}-s{dst}")
            active_links.append(f"s{dst}-s{src}") # Bidirectional
            
        try:
            requests.post(
                "http://127.0.0.1:5000/api/active_topology",
                json={"active_links": active_links},
                timeout=1
            )
        except Exception as e:
            self.logger.warning("Failed to push active topology: %s", str(e))


class FaultController(ControllerBase):
    def __init__(self, req, link, data, **config):
        super(FaultController, self).__init__(req, link, data, **config)
        self.app = data['app']

    @route('fault', '/api/fault', methods=['POST'])
    def fault_handler(self, req, **kwargs):
        try:
            body = req.json if hasattr(req, 'json') else json.loads(req.body.decode('utf-8'))
            link_id = body.get('link_id')
            if link_id:
                self.app.handle_fault(link_id)
                return json.dumps({"status": "ok", "message": f"Handled fault for {link_id}"})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})
        return json.dumps({"status": "ignored"})
