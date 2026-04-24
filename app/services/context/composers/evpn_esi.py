from __future__ import annotations


def compose_evpn_esi(
    *,
    device_ctx: dict,
    evpn_esi_intent: dict,
    ) -> dict:
        """
        Returns device-level EVPN EVI render context.
        
        """

        # Shallow copy is enough; intent is already device-scoped
        evpn_esi_ctx = {
            k: v
            for k, v in evpn_esi_intent.items()
        }        
        
        return evpn_esi_ctx