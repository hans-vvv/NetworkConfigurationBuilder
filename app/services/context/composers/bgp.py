from __future__ import annotations


def compose_bgp(
    *,
    device_ctx: dict,
    bgp_intent: dict,
    ) -> dict:
        """
        Returns device-level BGP render context.        
        """
        
        bgp_ctx = {
            k: v
            for k, v in bgp_intent.items()
        }

        return bgp_ctx