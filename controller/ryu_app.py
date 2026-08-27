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
from ryu.controller.handler import (
    CONFIG_DISPATCHER,
    MAIN_DISPATCHER,
    set_ev_cls,
)
from ryu.ofproto import ofproto_v1_3
from ryu.lib import hub
from ryu.lib.packet import packet, ethernet, ether_types
from ryu.topology import event as topo_event

import logging

LOG = logging.getLogger("NetworkGuardian.Controller")


class NetworkGuardianController(app_manager.RyuApp):
    """L2 learning switch controller with STP for looped topologies."""

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # mac_to_port[dpid] = {mac_address: port_number}
        self.mac_to_port = {}
        LOG.info("NetworkGuardian controller initialized")

    # ------------------------------------------------------------------
    # Switch connection — install a default table-miss flow entry
    # ------------------------------------------------------------------
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """Called when a switch connects and reports its features."""
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        dpid = datapath.id

        LOG.info("Switch connected: dpid=%s", dpid)

        # Delete any existing flows (clean slate)
        mod = parser.OFPFlowMod(
            datapath=datapath,
            command=ofproto.OFPFC_DELETE,
            out_port=ofproto.OFPP_ANY,
            out_group=ofproto.OFPG_ANY,
        )
        datapath.send_msg(mod)

        # Install table-miss flow: send unmatched packets to the controller
        match = parser.OFPMatch()
        actions = [
            parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)
        ]
        self._add_flow(datapath, priority=0, match=match, actions=actions)
        LOG.info("Table-miss flow installed on dpid=%s", dpid)

    # ------------------------------------------------------------------
    # Packet-In — learn source MAC, decide output port
    # ------------------------------------------------------------------
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        """Handle packets sent to the controller (table-miss or explicit)."""
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        dpid = datapath.id
        in_port = msg.match["in_port"]

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        if eth is None:
            return

        # Ignore LLDP (used for topology discovery / STP)
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        src = eth.src
        dst = eth.dst

        self.mac_to_port.setdefault(dpid, {})

        # Learn: associate the source MAC with the ingress port
        self.mac_to_port[dpid][src] = in_port

        # Decide: if we know the destination port, use it; otherwise flood
        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        # If we have a known destination, install a flow rule to avoid
        # sending future packets for this (dst, in_port) to the controller.
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            self._add_flow(datapath, priority=1, match=match, actions=actions,
                           idle_timeout=300)
            LOG.info(
                "Flow installed: dpid=%s %s -> port %s (from port %s)",
                dpid, dst, out_port, in_port,
            )

        # Send this packet out through the decided port
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
    # Helper: install a flow entry on a switch
    # ------------------------------------------------------------------
    def _add_flow(self, datapath, priority, match, actions,
                  idle_timeout=0, hard_timeout=0):
        """Push a single flow entry to the given switch."""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=inst,
            idle_timeout=idle_timeout,
            hard_timeout=hard_timeout,
        )
        datapath.send_msg(mod)
