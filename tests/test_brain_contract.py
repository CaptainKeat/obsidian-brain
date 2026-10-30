import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import obsidian_brain_mcp as mcp
from scripts.sync_skill import sync


class ContractTests(unittest.TestCase):
    def test_mcp_advertises_revision_and_history_arguments(self):
        tools = asyncio.run(mcp.mcp.list_tools())
        schemas = {tool.name: tool.inputSchema for tool in tools}
        self.assertIn("expected_sha256", schemas["obsidian_save_memory"]["properties"])
        self.assertIn("mode", schemas["obsidian_search"]["properties"])

    def test_mcp_revision_preserves_omitted_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(mcp.brain_memory, "DEFAULT_ROOTS", {"vault": Path(temp)}):
                first = mcp.obsidian_save_memory("Contract", "One", "fact", status="observed", project="Brain")
                first = json.loads(first.split("\n", 1)[1])
                second = mcp.obsidian_save_memory("Contract", "Two", "fact", status="stale", expected_sha256=first["sha256"])
                second = json.loads(second.split("\n", 1)[1])
                self.assertEqual(second["metadata"]["project"], "Brain")
                self.assertEqual(second["metadata"]["status"], "stale")

    def test_skill_sync_is_read_only_by_default_and_preserves_other_files(self):
        with tempfile.TemporaryDirectory() as temp:
            source, target = Path(temp)/"source", Path(temp)/"target"
            (source/"references").mkdir(parents=True)
            target.mkdir()
            (source/"SKILL.md").write_text("new")
            (source/"references/schema.md").write_text("reference")
            (target/"SKILL.md").write_text("old")
            (target/"other.txt").write_text("keep")
            self.assertEqual(len(sync(source, [target])), 2)
            self.assertEqual((target/"SKILL.md").read_text(), "old")
            sync(source, [target], apply=True)
            self.assertEqual(sync(source, [target]), [])
            self.assertEqual((target/"other.txt").read_text(), "keep")
            self.assertEqual(next(target.glob("SKILL.md.bak-*")).read_text(), "old")
