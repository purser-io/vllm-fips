# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project
"""Guards against hash calls that crash vLLM on FIPS-enabled hosts."""

from pathlib import Path

import pytest

from tools.pre_commit.check_fips_hashlib import check_file

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "source",
    [
        "import hashlib\nhashlib.md5(b'x')",
        "import hashlib\nhashlib.md5(b'x', usedforsecurity=True)",
        "import hashlib\nhashlib.blake2s(b'x')",
        "import hashlib\nhashlib.blake2b(b'x', digest_size=16)",
        "import hashlib\nhashlib.blake2b(b'x', digest_size=16, usedforsecurity=False)",
        "import hashlib\nhashlib.new('MD5')",
        "from hashlib import md5\nmd5(b'x')",
        "from hashlib import md5 as h\nh(b'x')",
        "import hmac, hashlib\nhmac.new(b'k', b'm', hashlib.md5)",
        "import hmac\nhmac.new(b'k', digestmod='md5')",
        "import hmac\nhmac.digest(b'k', b'm', 'md5')",
    ],
)
def test_rejects_fips_unsafe_calls(tmp_path, source):
    path = tmp_path / "mod.py"
    path.write_text(source)
    assert len(check_file(str(path))) == 1


@pytest.mark.parametrize(
    "source",
    [
        "import hashlib\nhashlib.md5(b'x', usedforsecurity=False)",
        "import hashlib\nhashlib.blake2b(b'x', usedforsecurity=False)",
        "import hashlib\nhashlib.new('md5', usedforsecurity=False)",
        "import hashlib\nhashlib.sha256(b'x').digest()[:16]",
        "import hashlib\nhashlib.sha1(b'x')",
        "import hmac, hashlib\nhmac.new(b'k', b'm', hashlib.sha256)",
    ],
)
def test_accepts_fips_safe_calls(tmp_path, source):
    path = tmp_path / "mod.py"
    path.write_text(source)
    assert check_file(str(path)) == []


def test_vllm_package_is_fips_safe():
    files = sorted((REPO_ROOT / "vllm").rglob("*.py"))
    assert files
    errors = [e for f in files for e in check_file(str(f))]
    assert errors == []
