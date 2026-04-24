from __future__ import annotations


def compose_sr(
    *,
    device_ctx: dict,
    sr_intent: dict,
    ) -> dict:
        """
        Returns device-level SR render context.
        
        """

        # Shallow copy is enough; intent is already device-scoped
        sr_ctx = {
            k: v
            for k, v in sr_intent.items()
        }        
        
        return sr_ctx