from __future__ import annotations

from typing import Any


def compose_evpn_l2vpn(
    *,
    device_ctx: dict[str, Any],
    evpn_l2vpn_intent: dict[str, Any],
) -> dict[str, Any]:
    """
    Attach EVPN L2VPN services as VLAN-based subinterfaces.

    Mutates ``device_ctx["interfaces"]`` in place and returns
    device-local EVPN L2VPN context.
    """
    variant_map: dict[str, dict[str, Any]] = evpn_l2vpn_intent.get("variant", {})
    interfaces: list[dict[str, Any]] = device_ctx.setdefault("interfaces", [])

    interface_by_name = {iface["name"]: iface for iface in interfaces}

    evpn_l2vpn_ctx: dict[str, Any] = {"variant": {}}

    for variant_name, variant_data in variant_map.items():
        variant_ctx: dict[str, Any] = {}
        evpn_l2vpn_ctx["variant"][variant_name] = variant_ctx

        for l2vpn_name, l2vpn_data in variant_data.items():
            service_ctx = {
                key: value
                for key, value in l2vpn_data.items()
                if key != "interfaces"
            }

            vlan = service_ctx["s_vlan"]
            variant_ctx[l2vpn_name] = service_ctx

            attachments = sorted(
                l2vpn_data.get("interfaces", []),
                key=lambda item: item["iface_name"],
            )

            for attachment in attachments:
                iface_name = attachment["iface_name"]
                iface = interface_by_name.get(iface_name)

                if iface is None:
                    raise RuntimeError(
                        f"EVPN L2VPN attachment on unknown interface '{iface_name}' "
                        f"on device {device_ctx['hostname']}"
                    )

                if iface["render_type"] not in ("lag_parent", "physical"):
                    raise RuntimeError(
                        f"EVPN L2VPN cannot attach to render_type "
                        f"'{iface['render_type']}' on interface '{iface_name}'"
                    )

                subifs: list[dict[str, Any]] = iface.setdefault("subinterfaces", [])

                subif_name = f"{iface_name}.{vlan}"

                service_attachment = {
                    "service": l2vpn_name,
                    **{k: v for k, v in attachment.items() if k != "iface_name"},
                }

                existing = next(
                    (si for si in subifs if si.get("name") == subif_name),
                    None,
                )

                if existing is None:
                    subifs.append(
                        {
                            "id": vlan,
                            "name": subif_name,
                            "evpn_l2vpn": service_attachment,
                        }
                    )
                else:
                    existing["id"] = vlan
                    existing["evpn_l2vpn"] = service_attachment

                subifs.sort(key=lambda si: si["id"])

    return evpn_l2vpn_ctx