# Swallo v0.1.4 Production Release Runbook

This document contains the exact click-by-click instructions and manual commands required to execute or recover the v0.1.4 release.

---

### Phase A: Pre-Release & Gating
1. **Verify Release Gate Checklist:** Ensure all items in `Step 6: GATE` are confirmed with evidence links.
2. **Quota Confirmation:** Verify maintainer quota is at least 25% before proceeding to publish.

---

### Phase B: PR Merge & Tagging
1. **Merge Release PR:**
   ```bash
   gh pr merge <PR_NUMBER> --merge --delete-branch
   ```
2. **Synchronize Local Main:**
   ```bash
   git checkout main
   git pull origin main
   ```
3. **Create and Push Annotated Release Tag:**
   ```bash
   git tag -a v0.1.4 -m "Release v0.1.4: deterministic tamper mutations, new-user golden path verification, and documentation hardening"
   git push origin v0.1.4
   ```

---

### Phase C: Deployment Environment Approval
1. Pushing tag `v0.1.4` automatically triggers `.github/workflows/release.yml`.
2. Monitor run:
   ```bash
   gh run list --workflow=release.yml --limit 1
   ```
3. Once `build` and `provenance` complete, navigate to the run URL on GitHub:
   `https://github.com/raunaknayak12/swallo/actions/runs/<RUN_ID>`
4. Click **"Review deployments"** in the top banner.
5. Select the checkbox for **`pypi`**.
6. Click **"Approve and deploy"**.

---

### Phase D: Post-Publish Verification
1. Verify package availability on PyPI:
   ```bash
   python -c "import urllib.request, json; data = json.loads(urllib.request.urlopen('https://pypi.org/pypi/swallo/json').read().decode()); print('Latest:', data['info']['version'])"
   ```
2. In an isolated virtual environment outside the repository:
   ```bash
   python -m venv C:\swallo-qa\verify-014\venv
   & C:\swallo-qa\verify-014\venv\Scripts\python.exe -m pip install swallo==0.1.4
   & C:\swallo-qa\verify-014\venv\Scripts\python.exe -W error -c "import swallo"
   & C:\swallo-qa\verify-014\venv\Scripts\python.exe -m swallo.cli doctor
   ```

---

### Phase E: Yank Deprecated Versions on PyPI
1. Go to [PyPI Manage Releases](https://pypi.org/manage/project/swallo/releases/).
2. Locate version `0.1.2`, click **Options** -> **Yank version**.
   * Reason: `Superseded by v0.1.4: fixes schema validation, approval flow normalization, and doctor workspace checks.`
3. If version `0.1.3` is also superseded:
   * Reason: `Superseded by v0.1.4: includes deterministic benchmark harness and documentation hardening.`

---

### Phase F: Rollback Procedure (Emergency Only)
* If critical flaws are detected immediately post-publish:
  1. Do **NOT** delete or re-tag git commits.
  2. Immediately navigate to PyPI Manage Releases and **Yank v0.1.4** with an explanatory reason.
  3. Prepare patch `v0.1.5` on a fix branch following the standard verification pipeline.
