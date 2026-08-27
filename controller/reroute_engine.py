"""
NetworkGuardian — Reroute Engine

Models the physical switch topology as a networkx graph and provides:
  - Shortest-path computation (Dijkstra) for unicast forwarding.
  - Minimum Spanning Tree (MST) computation for loop-free flooding.
  - Scoped link removal with affected-switch identification so the
    controller can clear flows only on switches adjacent to a failed link
    instead of wiping all switches globally.
"""

import networkx as nx
import logging

LOG = logging.getLogger("NetworkGuardian.RerouteEngine")


class RerouteEngine:
    def __init__(self):
        self.graph = nx.Graph()
        self.port_map = {}
        self._build_initial_topology()

    def _add_link(self, s1, s2, port1, port2):
        self.graph.add_edge(s1, s2)
        self.port_map[(s1, s2)] = port1
        self.port_map[(s2, s1)] = port2

    def _build_initial_topology(self):
        """Build baseline graph with exact Mininet port bindings."""
        for i in range(1, 5):
            self.graph.add_node(i)

        self._add_link(1, 2, 3, 1)  # s1(port 3) <-> s2(port 1)
        self._add_link(2, 3, 2, 4)  # s2(port 2) <-> s3(port 4)
        self._add_link(1, 4, 4, 4)  # s1(port 4) <-> s4(port 4)
        self._add_link(4, 3, 5, 5)  # s4(port 5) <-> s3(port 5)

    # ------------------------------------------------------------------
    # Link ID parsing
    # ------------------------------------------------------------------

    def parse_link_id(self, link_id: str):
        """Converts 's1-s2' to (1, 2).  Returns (None, None) on failure."""
        try:
            parts = link_id.replace('s', '').split('-')
            return int(parts[0]), int(parts[1])
        except Exception:
            return None, None

    def is_switch_link(self, link_id: str) -> bool:
        """Return True if *link_id* names a switch-to-switch link (e.g. 's1-s2').

        Host-switch links like 'h1-s1' are NOT switch links and do not need
        rerouting — they represent edge connectivity, not core topology.
        """
        return link_id.startswith('s') and '-s' in link_id

    # ------------------------------------------------------------------
    # Topology mutation
    # ------------------------------------------------------------------

    def remove_link(self, link_id: str):
        """Remove *link_id* from the graph.

        Returns ``(dpid1, dpid2)`` if the edge existed and was removed,
        or ``None`` if the edge was already gone or invalid.  The caller
        uses the returned pair to scope flow clears to only these two
        switches.
        """
        node1, node2 = self.parse_link_id(link_id)
        if node1 and node2 and self.graph.has_edge(node1, node2):
            self.graph.remove_edge(node1, node2)
            LOG.info("Removed link %s (switches %s, %s)", link_id, node1, node2)
            return (node1, node2)
        return None

    # ------------------------------------------------------------------
    # Path computation
    # ------------------------------------------------------------------

    def get_shortest_path(self, src_dpid: int, dst_dpid: int):
        try:
            return nx.shortest_path(self.graph, src_dpid, dst_dpid)
        except nx.NetworkXNoPath:
            return None

    def get_port_for_next_hop(self, current_dpid: int, next_dpid: int):
        """Retrieve the local port number connecting to the next-hop switch."""
        return self.port_map.get((current_dpid, next_dpid))

    def compute_all_paths(self):
        """Compute all-pairs shortest paths using Dijkstra's algorithm."""
        paths = {}
        for src in self.graph.nodes():
            paths[src] = {}
            for dst in self.graph.nodes():
                if src != dst:
                    try:
                        paths[src][dst] = nx.shortest_path(self.graph, src, dst)
                    except nx.NetworkXNoPath:
                        paths[src][dst] = None
        return paths

    # ------------------------------------------------------------------
    # Port classification helpers
    # ------------------------------------------------------------------

    def is_internal_port(self, dpid: int, port: int) -> bool:
        """Check if a port connects to another switch."""
        for (src, dst), p in self.port_map.items():
            if src == dpid and p == port:
                return True
        return False

    def get_flood_ports(self, dpid: int):
        """Returns internal ports that should be used for flooding.

        Computes a Minimum Spanning Tree of the current active graph to
        prevent broadcast storms, then returns only the MST ports for
        *dpid*.  Edge (host-facing) ports are handled separately by the
        controller.
        """
        mst = nx.minimum_spanning_tree(self.graph)

        mst_ports = []
        if dpid in mst.nodes():
            for neighbor in mst.neighbors(dpid):
                mst_ports.append(self.port_map[(dpid, neighbor)])

        return mst_ports
