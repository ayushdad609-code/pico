"""
Skill Gifting Engine for Pico (Feature F8).
Allows users to package, export, sign, and gift verified Hermes-distilled procedural skills
to friends with complete provenance and recipient consent gating.
"""

from __future__ import annotations
import os
import json
import hmac
import hashlib
import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
from pico.skills.skill_manage import SkillManageSkill
from pico.mcp_host import MCPHost


SECRET_SALT = os.environ.get("PICO_GIFT_SECRET") or "pico_hermes_skill_gift_salt_2026"


@dataclass
class GiftedSkillPackage:
    skill_name: str
    creator: str
    description: str
    parameters_schema: Dict[str, Any]
    code: str
    run_count: int
    success_rate: float
    creator_approved_at: str
    exported_at: str
    signature: str

    def to_bundle(self) -> str:
        data = {
            "pico_skill_gift": "v1.0",
            "name": self.skill_name,
            "creator": self.creator,
            "description": self.description,
            "parameters_schema": self.parameters_schema,
            "code": self.code,
            "provenance": {
                "run_count": self.run_count,
                "success_rate": self.success_rate,
                "creator_approved_at": self.creator_approved_at,
                "exported_at": self.exported_at
            },
            "signature": self.signature
        }
        raw_json = json.dumps(data, indent=2)
        return base64.b64encode(raw_json.encode("utf-8")).decode("utf-8")


class SkillGiftingEngine:
    """Manages exporting, verifying, and recipient-approved installation of gifted skills."""

    @staticmethod
    def _compute_signature(name: str, creator: str, code: str) -> str:
        msg = f"{name}:{creator}:{code}:{SECRET_SALT}".encode("utf-8")
        return hashlib.sha256(msg).hexdigest()[:24]

    @classmethod
    def export_skill(
        cls,
        name: str,
        creator: str,
        description: str,
        code: str,
        parameters_schema: Optional[Dict[str, Any]] = None,
        run_count: int = 5,
        success_rate: float = 1.0,
        creator_approved_at: Optional[str] = None
    ) -> GiftedSkillPackage:
        """Packages an approved skill with full provenance into a giftable bundle."""
        now_iso = datetime.now(timezone.utc).isoformat()
        approved_at = creator_approved_at or now_iso
        sig = cls._compute_signature(name, creator, code)

        return GiftedSkillPackage(
            skill_name=name,
            creator=creator,
            description=description,
            parameters_schema=parameters_schema or {},
            code=code,
            run_count=run_count,
            success_rate=success_rate,
            creator_approved_at=approved_at,
            exported_at=now_iso,
            signature=sig
        )

    @classmethod
    def unpack_gift_bundle(cls, bundle_str: str) -> Tuple[bool, Optional[GiftedSkillPackage], str]:
        """Validates bundle signature and extracts gifted skill metadata."""
        try:
            raw_bytes = base64.b64decode(bundle_str.encode("utf-8"))
            data = json.loads(raw_bytes.decode("utf-8"))
            if data.get("pico_skill_gift") != "v1.0":
                return False, None, "Invalid skill bundle format."

            name = data["name"]
            creator = data["creator"]
            code = data["code"]
            prov = data.get("provenance", {})

            expected_sig = cls._compute_signature(name, creator, code)
            if not hmac.compare_digest(data.get("signature", ""), expected_sig):
                return False, None, "Signature mismatch: gifted skill has been tampered with."

            pkg = GiftedSkillPackage(
                skill_name=name,
                creator=creator,
                description=data.get("description", ""),
                parameters_schema=data.get("parameters_schema", {}),
                code=code,
                run_count=prov.get("run_count", 1),
                success_rate=prov.get("success_rate", 1.0),
                creator_approved_at=prov.get("creator_approved_at", "unknown"),
                exported_at=prov.get("exported_at", "unknown"),
                signature=data["signature"]
            )
            return True, pkg, "Gifted skill bundle verified successfully."
        except Exception as e:
            return False, None, f"Failed to unpack gift bundle: {str(e)}"

    @classmethod
    def install_gift(
        cls,
        package: GiftedSkillPackage,
        mcp_host: MCPHost,
        user_approved: bool = False
    ) -> Tuple[bool, str]:
        """
        Installs the gifted skill only if the recipient explicitly approves (Gated Consent).
        """
        if not user_approved:
            return False, f"Consent required: Recipient must approve installing '{package.skill_name}' gifted by {package.creator}."

        payload = {
            "action": "create",
            "name": package.skill_name,
            "description": f"[Gifted by {package.creator}] {package.description}",
            "parameters_schema": package.parameters_schema,
            "code": package.code
        }

        success, msg, _ = mcp_host.execute_tool("skill_manage", payload, user_approved=True)
        if success:
            from pico.mcp_host import PermissionLevel
            mcp_host.register_tool(
                server_name="custom_gifted_skills",
                name=package.skill_name,
                description=payload["description"],
                permission_level=PermissionLevel.SEE
            )
            return True, f"✨ Successfully installed gifted skill '{package.skill_name}' from {package.creator}!"
        return False, f"Failed to install gifted skill: {msg}"
