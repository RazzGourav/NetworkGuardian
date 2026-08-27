"""
NetworkGuardian — Ryu SDN Controller Application

An L2 learning switch with STP (Spanning Tree Protocol) support for
loop-free forwarding on the NetworkGuardian redundant topology.

How it works:
  1. STP runs on all switches to elect a root bridge and block redundant
     ports, preventing broadcast storms.
  2. Once STP converges (ports reach FORWARD state), the controller learns
     MAC-to-port mappings via Packet-In events.
  3. Flows are installed for known destinations; unknown destinations are
     flooded only through STP-forwarding ports.
  4. Blocked ports are kept alive for failover — when a link goes down,
     STP reconverges and unblocks an alternate path.

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

# Add project root to path for imports if needed
sys.path.insert(0, "/app")
from controller.reroute_engine import RerouteEngine

LOG = logging.getLogger("NetworkGuardian.Controller")

class NetworkGuardianController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {'wsgi': WSGIApplication}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mac_to_switch = {}      # mac -> dpid
        self.mac_to_edge_port = {}   # mac -> port on that switch
        self.datapaths = {}          # dpid -> datapath object
        self.reroute_engine = RerouteEngine()
        
        wsgi = kwargs['wsgi']
        wsgi.register(FaultController, {'app': self})
        self.logger.info("NetworkGuardian controller initialized with WSGI and Reroute Engine")

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        dpid = datapath.id

        self.datapaths[dpid] = datapath
        self.logger.info("Switch connected: dpid=%s", dpid)

        # Install table-miss flow
        self.clear_flows(datapath)

    def clear_flows(self, datapath):
        """Clears all flows on a datapath and reinstalls table-miss."""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        # Delete flows
        mod = parser.OFPFlowMod(
            datapath=datapath,
            command=ofproto.OFPFC_DELETE,
            out_port=ofproto.OFPP_ANY,
            out_group=ofproto.OFPG_ANY,
        )
        datapath.send_msg(mod)

        # Install table-miss
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self._add_flow(datapath, priority=0, match=match, actions=actions)

        self.logger.debug("Flows cleared on dpid=%s", datapath.id)

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

        # We assume host connects to exactly one switch edge port
        # Only learn if it's not a known switch-to-switch port?
        # Actually, if we see it on an edge port, we learn it. 
        # But if we see it arriving from a switch-to-switch link, we shouldn't map it to that link!
        # Since RerouteEngine knows switch-to-switch ports, let's avoid learning from them.
        is_inter_switch_port = False
        for (s1, s2), port in self.reroute_engine.port_map.items():
            if s1 == dpid and port == in_port:
                is_inter_switch_port = True
                break
                
        # Learn the MAC address to avoid FLOOD next time, but ONLY if it came from an edge port!
        # If it came from an internal switch-to-switch port, the source host is NOT attached to this switch.
        if not self.reroute_engine.is_internal_port(dpid, in_port):
            self.mac_to_switch[src] = dpid
            self.mac_to_edge_port[src] = in_port

        # Decide output port
        out_port = ofproto.OFPP_FLOOD
        
        is_flooding = False
        if dst in self.mac_to_switch:
            dst_dpid = self.mac_to_switch[dst]
            
            if dst_dpid == dpid:
                # Same switch, output to edge port
                out_port = self.mac_to_edge_port[dst]
            else:
                # Need to route to different switch
                path = self.reroute_engine.get_shortest_path(dpid, dst_dpid)
                if path and len(path) > 1:
                    next_hop = path[1]
                    out_port = self.reroute_engine.get_port_for_next_hop(dpid, next_hop)
                else:
                    self.logger.error("No path from %s to %s", dpid, dst_dpid)
                    return
            
            actions = [parser.OFPActionOutput(out_port)]
        else:
            is_flooding = True
            actions = []
            
            # Flooding logic: flood to all edge ports + MST active internal ports
            mst_ports = self.reroute_engine.get_flood_ports(dpid)
            
            # We don't have a definitive list of ALL ports here, but we can query them or just use OFPP_FLOOD?
            # Wait, if we use OFPP_FLOOD, it goes to ALL active ports.
            # But we ONLY want it to go to edge ports + mst_ports!
            # Since we know the max ports is 5, we can just iterate over 1..5.
            # A more robust way: use the datapath.ports dictionary.
            for port in datapath.ports.keys():
                if port == in_port or port >= ofproto.OFPP_MAX:
                    continue
                # If it's an internal port, it MUST be in the MST to be flooded
                if self.reroute_engine.is_internal_port(dpid, port):
                    if port in mst_ports:
                        actions.append(parser.OFPActionOutput(port))
                else:
                    # It's an edge port, always flood
                    actions.append(parser.OFPActionOutput(port))

        # Install a flow to avoid packet_in next time
        if not is_flooding:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            self._add_flow(datapath, priority=1, match=match, actions=actions, idle_timeout=30)
            
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

    def _add_flow(self, datapath, priority, match, actions, idle_timeout=0):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(
            datapath=datapath, priority=priority, match=match,
            instructions=inst, idle_timeout=idle_timeout,
        )
        datapath.send_msg(mod)

    def handle_fault(self, link_id):
        self.logger.warning("Fault received for link %s. Recomputing paths...", link_id)
        if self.reroute_engine.remove_link(link_id):
            # Clear all flows so traffic falls back to Packet-In and uses new shortest paths
            for datapath in self.datapaths.values():
                self.clear_flows(datapath)
            self.logger.info("Flows cleared on all switches. Traffic will route around %s", link_id)


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

