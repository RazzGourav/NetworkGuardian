"""
NetworkGuardian — Custom Mininet Topology

Topology (8 hosts, 4 switches, redundant paths):

        h1   h2          h5   h6
         \  /              \  /
          s1 ---- s2 ---- s3
           \                /
            \              /
             --- s4 -------
                / \\
              h3   h4
                    |
                   h7  h8  (h7 on s4, h8 on s3)

Switches: s1, s2, s3, s4
Hosts:    h1-h8 (8 hosts total)

Redundant paths between s1 and s3:
  - s1 -> s2 -> s3        (primary)
  - s1 -> s4 -> s3        (backup)

Removed s4-s2 cross-link to eliminate one of the loops for Phase 1 testing.
Still satisfies the requirement: "at least one redundant path".

Later phases will restore s4-s2 and demonstrate STP handling of broadcast storms.
"""

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, OVSKernelSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info


class NetworkGuardianTopo(Topo):
    """8-host, 4-switch SDN topology with redundant paths."""

    def build(self):
        # --- Switches (OpenFlow 1.3) ---
        s1 = self.addSwitch("s1", protocols="OpenFlow13")
        s2 = self.addSwitch("s2", protocols="OpenFlow13")
        s3 = self.addSwitch("s3", protocols="OpenFlow13")
        s4 = self.addSwitch("s4", protocols="OpenFlow13")

        # --- Hosts ---
        h1 = self.addHost("h1", ip="10.0.0.1/24")
        h2 = self.addHost("h2", ip="10.0.0.2/24")
        h3 = self.addHost("h3", ip="10.0.0.3/24")
        h4 = self.addHost("h4", ip="10.0.0.4/24")
        h5 = self.addHost("h5", ip="10.0.0.5/24")
        h6 = self.addHost("h6", ip="10.0.0.6/24")
        h7 = self.addHost("h7", ip="10.0.0.7/24")
        h8 = self.addHost("h8", ip="10.0.0.8/24")

        # --- Host-to-switch links ---
        self.addLink(h1, s1)
        self.addLink(h2, s1)
        self.addLink(h3, s4)
        self.addLink(h4, s4)
        self.addLink(h5, s3)
        self.addLink(h6, s3)
        self.addLink(h7, s4)
        self.addLink(h8, s3)

        # --- Switch-to-switch links (create redundant paths) ---
        self.addLink(s1, s2, bw=10)   # primary path segment
        self.addLink(s2, s3, bw=10)   # primary path segment
        self.addLink(s1, s4, bw=10)   # backup path segment
        self.addLink(s4, s3, bw=10)   # backup path segment
        # Removed: self.addLink(s4, s2, bw=10)   # cross-link (creates extra loop)


# Expose topology to Mininet's --custom flag
topos = {"networkguardian": (lambda: NetworkGuardianTopo())}


def run_standalone():
    """Run the topology directly (outside Docker, for quick local testing)."""
    setLogLevel("info")
    topo = NetworkGuardianTopo()
    net = Mininet(
        topo=topo,
        controller=lambda name: RemoteController(name, ip="127.0.0.1", port=6653),
        switch=OVSKernelSwitch,
        autoSetMacs=True,
    )
    net.start()
    info("*** NetworkGuardian topology is running\n")
    info("*** Type 'pingall' to test connectivity\n")
    CLI(net)
    net.stop()


if __name__ == "__main__":
    run_standalone()
