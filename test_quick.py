# -*- coding: utf-8 -*-
import sys
from pathlib import Path

# Add paths
ROOT = Path(__file__).parent.resolve()
TOOL = ROOT.parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TOOL))

print("\n" + "="*60)
print("DRY RUN TEST")
print("="*60)

# Test 1: Imports
print("\n[1/5] Testing imports...")
try:
    from social_auto_upload_tool import ContentAutomationAgent
    from social_auto_upload.utils.yunlogin_api import YunLoginAPI
    from social_auto_upload.uploader.tk_uploader.main import TiktokVideo
    print("      [OK] All modules imported")
except Exception as e:
    print(f"      [FAIL] {e}")

# Test 2: Config
print("\n[2/5] Testing config...")
try:
    from conf import BASE_DIR
    print(f"      [OK] Base dir: {BASE_DIR}")
except Exception as e:
    print(f"      [FAIL] {e}")

# Test 3: YunLogin API
print("\n[3/5] Testing YunLogin API...")
try:
    from social_auto_upload.utils.yunlogin_api import YunLoginAPI
    api = YunLoginAPI()
    status = api.check_status()
    if status:
        envs = api.get_all_environments()
        print(f"      [OK] YunLogin running, {len(envs) if envs else 0} envs found")
    else:
        print("      [WARN] YunLogin not running")
except Exception as e:
    print(f"      [FAIL] {e}")

# Test 4: Database
print("\n[4/5] Testing database...")
try:
    from social_auto_upload_tool import VideoDatabase
    db = VideoDatabase()
    print(f"      [OK] DB path: {db.db_path}")
except Exception as e:
    print(f"      [FAIL] {e}")

# Test 5: FFmpeg
print("\n[5/5] Testing FFmpeg...")
try:
    import subprocess
    result = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=3)
    if result.returncode == 0:
        print("      [OK] FFmpeg installed")
    else:
        print("      [FAIL] FFmpeg command failed")
except Exception as e:
    print(f"      [FAIL] {e}")

print("\n" + "="*60)
print("TEST COMPLETE")
print("="*60)
