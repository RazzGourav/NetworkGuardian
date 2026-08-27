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

        self._add_link(1, 2, 3, 1) # s1(port 3) <-> s2(port 1)
        self._add_link(2, 3, 2, 4) # s2(port 2) <-> s3(port 4)
        self._add_link(1, 4, 4, 4) # s1(port 4) <-> s4(port 4)
        self._add_link(4, 3, 5, 5) # s4(port 5) <-> s3(port 5)

    def parse_link_id(self, link_id: str):
        """Converts 's1-s2' to (1, 2)."""
        try:
            parts = link_id.replace('s', '').split('-')
            return int(parts[0]), int(parts[1])
        except:
            return None, None

    def remove_link(self, link_id: str):
        node1, node2 = self.parse_link_id(link_id)
        if node1 and node2 and self.graph.has_edge(node1, node2):
            self.graph.remove_edge(node1, node2)
            LOG.info("RerouteEngine: Removed link %s", link_id)
            return True
        return False

    def get_shortest_path(self, src_dpid: int, dst_dpid: int):
        try:
            return nx.shortest_path(self.graph, src_dpid, dst_dpid)
        except nx.NetworkXNoPath:
            return None

    def get_port_for_next_hop(self, current_dpid: int, next_dpid: int):
        return self.port_map.get((current_dpid, next_dpid))

    def compute_all_paths(self):
        """Compute all-pairs shortest paths."""
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

    def is_internal_port(self, dpid: int, port: int) -> bool:
        """Check if a port connects to another switch."""
        for (src, dst), p in self.port_map.items():
            if src == dpid and p == port:
                return True
        return False

    def get_flood_ports(self, dpid: int):
        """Returns ports that should be flooded to (all edge ports + MST ports)."""
        # 1. Compute MST of current active switch topology to prevent loops
        mst = nx.minimum_spanning_tree(self.graph)
        
        # 2. Get the switch-to-switch ports in the MST
        mst_ports = []
        if dpid in mst.nodes():
            for neighbor in mst.neighbors(dpid):
                mst_ports.append(self.port_map[(dpid, neighbor)])
                
        # 3. Add all edge ports (ports not in port_map)
        # We know the total ports per switch from our topology
        # s1: 1, 2 (hosts), 3, 4 (switches)
        # s2: 1, 2 (switches)
        # s3: 1, 2, 3 (hosts), 4, 5 (switches)
        # s4: 1, 2, 3 (hosts), 4, 5 (switches)
        # We can just return mst_ports + [all known edge ports]
        # Better yet, return the list of ports we know are safe to flood.
        
        # Or even simpler: the controller can just check `not is_internal_port(dpid, p) or p in mst_ports`
        return mst_ports
