// NetworkGuardian Dashboard Logic

// --- Constants & Colors ---
const COLORS = {
    healthy: '#10b981',
    degraded: '#f59e0b',
    down: '#ef4444',
    host: '#3b82f6',
    switch: '#8b5cf6',
    text: '#f8f9fa',
    bg: '#0f111a'
};

// --- State ---
let topologyData = { nodes: [], links: [] };
let chartInstance = null;

// --- Initialize Chart.js ---
function initChart() {
    const ctx = document.getElementById('metricsChart').getContext('2d');
    
    Chart.defaults.color = '#8b92a5';
    Chart.defaults.font.family = 'Inter';
    
    chartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [], // Timestamps
            datasets: []
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    labels: { boxWidth: 12, usePointStyle: true }
                },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    backgroundColor: 'rgba(15, 17, 26, 0.9)',
                    titleColor: '#fff',
                    bodyColor: '#fff',
                    borderColor: 'rgba(255,255,255,0.1)',
                    borderWidth: 1
                }
            },
            scales: {
                x: {
                    display: false // Hide x-axis labels to save space
                },
                y: {
                    beginAtZero: true,
                    grid: { color: 'rgba(255,255,255,0.05)' }
                }
            },
            interaction: {
                mode: 'nearest',
                axis: 'x',
                intersect: false
            }
        }
    });
}

// --- Fetch & Render Metrics ---
async function fetchMetrics() {
    try {
        const response = await fetch('/api/metrics');
        const data = await response.json();
        
        // We will plot the top 3 most active/problematic links to avoid clutter
        // For simplicity, just pick a few switch-switch links if available, else first 3
        const linkIds = Object.keys(data).filter(id => id.includes('s')).slice(0, 3);
        
        if (linkIds.length === 0 && Object.keys(data).length > 0) {
            linkIds.push(...Object.keys(data).slice(0, 3));
        }

        const datasets = [];
        let labels = [];
        
        const lineColors = [COLORS.healthy, COLORS.host, COLORS.switch];
        
        linkIds.forEach((linkId, i) => {
            const linkData = data[linkId];
            if (!linkData) return;
            
            // Use the timestamps from the first link as x-axis
            if (labels.length === 0) {
                labels = linkData.timestamps.map(t => {
                    const d = new Date(t);
                    return `${d.getHours()}:${d.getMinutes()}:${d.getSeconds()}`;
                });
            }
            
            datasets.push({
                label: `${linkId} Latency`,
                data: linkData.latencies,
                borderColor: lineColors[i % lineColors.length],
                backgroundColor: 'transparent',
                borderWidth: 2,
                pointRadius: 0,
                pointHoverRadius: 4,
                tension: 0.4
            });
        });
        
        if (chartInstance) {
            chartInstance.data.labels = labels;
            chartInstance.data.datasets = datasets;
            chartInstance.update('none'); // Update without animation for smooth live feel
        }
        
    } catch (err) {
        console.error("Failed to fetch metrics:", err);
    }
}

// --- Fetch & Render Topology ---
let svg, simulation, link, node, labels;

function initD3() {
    const container = document.getElementById('topology-container');
    const width = container.clientWidth;
    const height = container.clientHeight;
    
    svg = d3.select("#topology-container")
        .append("svg")
        .attr("width", "100%")
        .attr("height", "100%")
        .attr("viewBox", [0, 0, width, height]);
        
    // Arrow marker for directed links (if needed, though ours are bidirectional)
    svg.append("defs").selectAll("marker")
        .data(["end"])
        .enter().append("marker")
        .attr("id", String)
        .attr("viewBox", "0 -5 10 10")
        .attr("refX", 25)
        .attr("refY", 0)
        .attr("markerWidth", 6)
        .attr("markerHeight", 6)
        .attr("orient", "auto")
        .append("path")
        .attr("fill", "rgba(255,255,255,0.3)")
        .attr("d", "M0,-5L10,0L0,5");

    simulation = d3.forceSimulation()
        .force("link", d3.forceLink().id(d => d.id).distance(100))
        .force("charge", d3.forceManyBody().strength(-400))
        .force("center", d3.forceCenter(width / 2, height / 2))
        .force("collide", d3.forceCollide().radius(40));
}

async function fetchTopology() {
    try {
        const response = await fetch('/api/topology');
        topologyData = await response.json();
        renderTopology();
        updateGlobalStatus();
    } catch (err) {
        console.error("Failed to fetch topology:", err);
    }
}

function renderTopology() {
    // Clear old elements
    svg.selectAll(".links").remove();
    svg.selectAll(".nodes").remove();
    svg.selectAll(".labels").remove();
    
    // Group links
    const linkGroup = svg.append("g").attr("class", "links");
    link = linkGroup.selectAll("line")
        .data(topologyData.links)
        .enter().append("line")
        .attr("class", "link")
        .attr("stroke-width", d => d.health === 'down' ? 1 : (d.health === 'degraded' ? 3 : 2))
        .attr("stroke", d => COLORS[d.health] || 'rgba(255,255,255,0.2)')
        .attr("stroke-dasharray", d => d.health === 'down' ? "5,5" : "none");

    // Group nodes
    const nodeGroup = svg.append("g").attr("class", "nodes");
    node = nodeGroup.selectAll("circle")
        .data(topologyData.nodes)
        .enter().append("circle")
        .attr("class", "node")
        .attr("r", d => d.type === 'switch' ? 20 : 14)
        .attr("fill", d => d.type === 'switch' ? COLORS.switch : COLORS.host)
        .attr("stroke", "rgba(255,255,255,0.2)")
        .attr("stroke-width", 2)
        .call(d3.drag()
            .on("start", dragstarted)
            .on("drag", dragged)
            .on("end", dragended));

    // Group labels
    const labelGroup = svg.append("g").attr("class", "labels");
    labels = labelGroup.selectAll("text")
        .data(topologyData.nodes)
        .enter().append("text")
        .attr("class", "node-label")
        .attr("dy", d => d.type === 'switch' ? 5 : 4)
        .text(d => d.id);

    simulation.nodes(topologyData.nodes).on("tick", ticked);
    simulation.force("link").links(topologyData.links);
    simulation.alpha(1).restart();
}

function ticked() {
    link
        .attr("x1", d => d.source.x)
        .attr("y1", d => d.source.y)
        .attr("x2", d => d.target.x)
        .attr("y2", d => d.target.y);

    node
        .attr("cx", d => d.x)
        .attr("cy", d => d.y);
        
    labels
        .attr("x", d => d.x)
        .attr("y", d => d.y);
}

// Drag functions
function dragstarted(event, d) {
    if (!event.active) simulation.alphaTarget(0.3).restart();
    d.fx = d.x;
    d.fy = d.y;
}
function dragged(event, d) {
    d.fx = event.x;
    d.fy = event.y;
}
function dragended(event, d) {
    if (!event.active) simulation.alphaTarget(0);
    d.fx = null;
    d.fy = null;
}

// --- Event Log & Status ---
function addLogEntry(type, message, timeStr = null) {
    const logContainer = document.getElementById('event-log');
    const entry = document.createElement('div');
    entry.className = `log-entry ${type}`;
    
    if (!timeStr) {
        const d = new Date();
        timeStr = `${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}:${d.getSeconds().toString().padStart(2,'0')}`;
    }
    
    entry.innerHTML = `
        <span class="time">${timeStr}</span>
        <span class="message">${message}</span>
    `;
    
    logContainer.prepend(entry);
    
    // Keep only last 50
    while(logContainer.children.length > 50) {
        logContainer.removeChild(logContainer.lastChild);
    }
}

function updateGlobalStatus() {
    const indicator = document.getElementById('global-status-indicator');
    const text = document.getElementById('global-status-text');
    
    const hasDown = topologyData.links.some(l => l.health === 'down');
    const hasDegraded = topologyData.links.some(l => l.health === 'degraded');
    
    indicator.className = 'status-indicator';
    if (hasDown) {
        indicator.classList.add('down');
        text.innerText = 'System: Fault Detected';
    } else if (hasDegraded) {
        indicator.classList.add('degraded');
        text.innerText = 'System: Degraded';
    } else {
        indicator.classList.add('healthy');
        text.innerText = 'System: OK';
    }
}

// --- WebSocket Setup ---
function setupWebSocket() {
    const socket = io();
    
    socket.on('connect', () => {
        addLogEntry('info', 'Connected to NetworkGuardian telemetry stream.');
    });
    
    socket.on('disconnect', () => {
        addLogEntry('warning', 'Disconnected from telemetry stream.');
    });
    
    socket.on('network_event', (data) => {
        // data: { timestamp, type, message, link_id }
        const d = new Date(data.timestamp);
        const timeStr = `${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}:${d.getSeconds().toString().padStart(2,'0')}`;
        
        let cssClass = 'info';
        if (data.type === 'fault') cssClass = 'fault';
        if (data.type === 'recovery') cssClass = 'recovery';
        if (data.type === 'warning') cssClass = 'warning';
        
        addLogEntry(cssClass, data.message, timeStr);
        
        // Immediately fetch new topology and metrics to reflect the event
        fetchTopology();
        fetchMetrics();
    });
}

// --- Main Initialization ---
window.addEventListener('DOMContentLoaded', () => {
    initChart();
    initD3();
    
    // Initial fetch
    fetchTopology();
    fetchMetrics();
    
    // Setup live stream
    setupWebSocket();
    
    // Fallback polling for metrics just in case (every 2s)
    setInterval(fetchMetrics, 2000);
});
