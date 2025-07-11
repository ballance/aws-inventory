import json
from pathlib import Path
import networkx as nx
import matplotlib.pyplot as plt
import argparse
from matplotlib.patches import Patch

LAYER_GAP = 3.0

def parse_args() -> Path:
    """Return the Path to the inventory folder supplied on the command line."""
    parser = argparse.ArgumentParser(
        description="Generate topology diagrams from AWS inventory JSON"
    )
    parser.add_argument(
        "folder",
        metavar="FOLDER",
        help="Directory created by inventory.sh that contains the *.json files",
    )
    args = parser.parse_args()
    return Path(args.folder).expanduser().resolve()

def main() -> None:
    folder = parse_args()

    with (folder / "vpcs.json").open() as f: vpcs = json.load(f)
    with (folder / "subnets.json").open() as f: subs = json.load(f)
    with (folder / "ec2-instances.json").open() as f: ec2s = json.load(f)
    with (folder / "rds-instances.json").open() as f: rds = json.load(f)
    with (folder / "ecs-clusters.json").open() as f: ecs = json.load(f)
    with (folder / "load-balancers.json").open() as f: lbs = json.load(f)
    with (folder / "ecs-services.json").open() as f: ecs_services = json.load(f)
    with (folder / "target-groups.json").open() as f: tgs = json.load(f)

    target_to_lb = {
        tg: lb["LoadBalancerArn"]
        for lb in lbs.get("LoadBalancers", [])
        for tg in lb.get("TargetGroupArns", [])
    }

    tg_to_vpc = {tg["TargetGroupArn"]: tg["VpcId"] for tg in tgs.get("TargetGroups", [])}

    used_lb_names = set()
    for svc in ecs_services.get("services", []):
        for lb in svc.get("loadBalancers", []):
            lb_name = lb.get("loadBalancerName")
            tg_arn = lb.get("targetGroupArn", "")
            if lb_name:
                used_lb_names.add(lb_name)
            elif tg_arn:
                parts = tg_arn.split(":")[-1].split("/")
                if len(parts) >= 2:
                    used_lb_names.add(parts[-2])

    G = nx.DiGraph()

    for v in vpcs["Vpcs"]:
        cidr = v.get("CidrBlock", "unknown")
        G.add_node(v["VpcId"], label=f"VPC\n{cidr}", color="skyblue", layer=2)

    for s in subs["Subnets"]:
        subnet_name = s.get("Tags", [{}])[0].get("Value", s["SubnetId"])
        G.add_node(s["SubnetId"], label=f"Subnet\n{subnet_name}", color="lightgreen", layer=1)
        G.add_edge(s["VpcId"], s["SubnetId"])

    for db in rds["DBInstances"]:
        db_id = db["DBInstanceIdentifier"]
        G.add_node(db_id, label="RDS", color="plum", layer=0)
        for sn in db.get("DBSubnetGroup", {}).get("Subnets", []):
            if sn_id := sn.get("SubnetIdentifier"):
                G.add_edge(sn_id, db_id)

    for lb in lbs["LoadBalancers"]:
        name = lb["LoadBalancerName"]
        if name in used_lb_names:
            lb_id = f"LB:{name}"
            G.add_node(lb_id, label="Load Balancer", color="lightslategray", layer=3)
            G.add_edge(lb["VpcId"], lb_id)

    for svc in ecs_services["services"]:
        svc_name = svc["serviceName"]
        cluster_name = svc["clusterArn"].split("/")[-1]

        cluster_id = f"CLUSTER:{cluster_name}"
        service_id = f"SVC:{svc_name}"

        G.add_node(cluster_id, label="ECS Cluster", color="lightyellow", layer=3)
        G.add_node(service_id, label=f"ECS Service\n{svc_name}", color="gold", layer=4)
        G.add_edge(cluster_id, service_id)

        for lb in svc.get("loadBalancers", []):
            tg_arn = lb.get("targetGroupArn", "")
            lb_name = lb.get("loadBalancerName") or tg_arn.split("/")[-2] if tg_arn else None

            if lb_name:
                lb_id = f"LB:{lb_name}"
                if not G.has_node(lb_id):
                    G.add_node(lb_id, label="Load Balancer", color="lightslategray", layer=3)
                G.add_edge(service_id, lb_id)

            # Map service to VPC through target group
            if tg_arn and tg_arn in tg_to_vpc:
                G.add_edge(tg_to_vpc[tg_arn], service_id)

    unattached = [
        n for n in G
        if G.in_degree(n) == 0 and G.nodes[n]["label"] in {
            "EC2", "RDS", "ECS Cluster", "ECS Task"
        }
    ]
    if unattached:
        NO_VPC = "NO_VPC"
        G.add_node(NO_VPC, label="No VPC", color="lightgray", layer=0)
        G.add_edges_from((NO_VPC, n) for n in unattached)

    def draw_vpc_topology(vpc_id, subgraph, title=None):
        for n in subgraph.nodes:
            subgraph.nodes[n].setdefault("layer", 99)
            subgraph.nodes[n].setdefault("color", "gray")
            subgraph.nodes[n].setdefault("label", n)
        pos = nx.multipartite_layout(subgraph, subset_key="layer", align="horizontal")
        pos = {n: (x * LAYER_GAP * 2, -subgraph.nodes[n]["layer"] * LAYER_GAP)
               for n, (x, _) in pos.items()}

        fig, ax = plt.subplots(figsize=(18, 8), constrained_layout=True)
        nx.draw_networkx_edges(subgraph, pos, ax=ax, arrows=True, arrowstyle="->", width=1.2)
        nx.draw_networkx_nodes(subgraph, pos, node_size=1800,
            node_color=[subgraph.nodes[n]["color"] for n in subgraph], ax=ax)

        for n, (x, y) in pos.items():
            short_name = n.split(":")[-1][:10] if ":" in n else n[:12]
            ax.text(x, y, f"{subgraph.nodes[n]['label']}\n{short_name}",
                    ha="center", va="center", fontsize=7,
                    bbox=dict(facecolor="white", alpha=0.85, lw=0))

        ax.set_title(title or f"Topology for {vpc_id}", pad=20)
        ax.axis("off")

        counts = {
            "VPC": len(vpcs["Vpcs"]),
            "Subnet": len(subs["Subnets"]),
            "EC2": sum(len(r["Instances"]) for r in ec2s["Reservations"]),
            "RDS": len(rds["DBInstances"]),
            "LB": len(used_lb_names),
            "Unattached": len([
                n for n in G
                if G.in_degree(n) == 0 and G.nodes[n]["label"] in {
                    "EC2", "RDS", "ECS Cluster", "ECS Task"
                }
            ])
        }
        legend_handles = [
            Patch(color="skyblue", label=f"VPCs ({counts['VPC']})"),
            Patch(color="lightgreen", label=f"Subnets ({counts['Subnet']})"),
            Patch(color="orange", label=f"EC2 instances ({counts['EC2']})"),
            Patch(color="plum", label=f"RDS instances ({counts['RDS']})"),
            Patch(color="lightslategray", label=f"Load Balancers ({counts['LB']})"),
            Patch(color="gold", label=f"ECS Services ({len(ecs_services['services'])})"),
        ]
        if counts["Unattached"]:
            legend_handles.append(
                Patch(color="lightgray", label=f"Unattached ({counts['Unattached']})")
            )
        ax.legend(handles=legend_handles, loc="lower center", ncol=4,
                  bbox_to_anchor=(0.5, -0.15), frameon=False, fontsize=8)

        fig.savefig(folder / f"{vpc_id}_topology.png", dpi=200)

    for vpc in vpcs["Vpcs"]:
        vpc_id = vpc["VpcId"]
        row_nodes = {vpc_id} | nx.descendants(G, vpc_id)
        draw_vpc_topology(vpc_id, G.subgraph(row_nodes).copy())

    if unattached:
        row_nodes = {NO_VPC} | nx.descendants(G, NO_VPC)
        draw_vpc_topology("NO_VPC", G.subgraph(row_nodes).copy(), title="Topology — Orphaned Resources")

if __name__ == "__main__":
    main()
