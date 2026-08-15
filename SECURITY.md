# Security Policy

> [!IMPORTANT]
> This repository is `purser-io/vllm-fips`, a Purser-maintained fork of
> [vllm-project/vllm](https://github.com/vllm-project/vllm). Route reports to
> whoever can fix them — see [Which project to report to](#which-project-to-report-to).

## Which project to report to

| Affected component | Report to |
| --- | --- |
| Fork-specific: `docker/Dockerfile.opencv-fips`, `tools/check_opencv_fips.py`, `custom-wheels/`, the FIPS wheel itself, or the resolver pinning in `docker/Dockerfile` | **Purser** — GitHub → Security → *Report a vulnerability* on [`purser-io/vllm-fips`](https://github.com/purser-io/vllm-fips/security/advisories/new), or email <security@purser-io.io> |
| vLLM itself (the engine, API server, scheduler, model code — anything inherited from upstream) | **vLLM** — [upstream vulnerability submission form](https://github.com/vllm-project/vllm/security/advisories/new) |
| `opencv-python` upstream, independent of this fork's packaging | [opencv/opencv-python](https://github.com/opencv/opencv-python/issues) |

If you are unsure, report to Purser and we will forward upstream under
coordinated disclosure rather than leave it unreported.

For Purser-handled reports we aim to acknowledge within **3 business days** and
follow coordinated disclosure (target ≤90 days), matching the policy in
[`purser-io/purser`](https://github.com/purser-io/purser/blob/main/SECURITY.md).

**Do not open a public issue for a vulnerability in either project.**

## Reporting security issues (upstream vLLM)

Please report security issues in vLLM itself privately using [the vulnerability submission form](https://github.com/vllm-project/vllm/security/advisories/new).

## Issue triage

Reports against upstream vLLM will then be triaged by the [vulnerability management team](https://docs.vllm.ai/en/latest/contributing/vulnerability_management.html). Reports against fork-specific components are triaged by Purser.

## Threat model

Please see the [Security Guide in the vLLM documentation](https://docs.vllm.ai/en/latest/usage/security.html) for more information on vLLM's security assumptions and recommendations.

Please see [PyTorch's Security Policy](https://github.com/pytorch/pytorch/blob/main/SECURITY.md) for more information and recommendations on how to securely interact with models.

## Issue severity

We will determine the risk of each issue, taking into account our experience dealing with past issues, versions affected, common defaults, and use cases. We use the following severity categories:

### CRITICAL Severity

Vulnerabilities that allow remote attackers to execute arbitrary code, take full control of the system, or significantly compromise confidentiality, integrity, or availability without any interaction or privileges needed, examples include remote code execution via network, deserialization issues that allow exploit chains. Generally those issues which are rated as CVSS  ≥ 9.0.

### HIGH Severity

Serious security flaws that allow elevated impact—like RCE in specific, limited contexts or significant data loss—but require advanced conditions or some trust, examples include RCE in advanced deployment modes (e.g. multi-node), or high impact issues where some sort of privileged network access is required. These issues typically have CVSS scores between 7.0 and 8.9

### MODERATE Severity

Vulnerabilities that cause denial of service or partial disruption, but do not allow arbitrary code execution or data breach and have limited impact. These issues have a CVSS rating between 4.0 and 6.9

### LOW Severity

Minor issues such as informational disclosures, logging errors, non-exploitable flaws, or weaknesses that require local or high-privilege access and offer negligible impact. Examples include side channel attacks or hash collisions. These issues often have CVSS scores less than 4.0

## Fix disclosure policy

When a security report is accepted, the fix process depends on the severity:

* **CRITICAL and HIGH severity**: Fixes are developed in a private security fork and coordinated with the prenotification group before public disclosure.
* **MODERATE and LOW severity**: Fixes are developed and submitted as public pull requests. These issues do not require embargo since they do not enable arbitrary code execution or significant data breach, and public visibility accelerates community review and adoption of the fix.

The vulnerability management team reserves the right to adjust the disclosure approach on a case-by-case basis, taking into account factors such as active exploitation, unusual attack surface, or coordination requirements with downstream vendors.

## Prenotification policy

For certain security issues of CRITICAL, HIGH, or MODERATE severity level, we may prenotify certain organizations or vendors that ship vLLM. The purpose of this prenotification is to allow for a coordinated release of fixes for severe issues.

* This prenotification will be in the form of a private email notification. It may also include adding security contacts to the GitHub security advisory, typically a few days before release.

* If you wish to be added to the prenotification group, please send an email copying all the members of the [vulnerability management team](https://docs.vllm.ai/en/latest/contributing/vulnerability_management.html). Each vendor contact will be analyzed on a case-by-case basis.

* Organizations and vendors who either ship or use vLLM, are eligible to join the prenotification group if they meet at least one of the following qualifications
    * Substantial internal deployment leveraging the upstream vLLM project.
    * Established internal security teams and comprehensive compliance measures.
    * Active and consistent contributions to the upstream vLLM project.

* We may withdraw organizations from receiving future prenotifications if they release fixes or any other information about issues before they are public. Group membership may also change based on policy refinements for who may be included.
