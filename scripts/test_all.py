"""
Run all tests at once
Run: python test_all.py
"""
import subprocess
import sys
import os

def run_test(test_name, script_name):
    print("\n" + "="*60)
    print(f"▶️  RUNNING: {test_name}")
    print("="*60)
    
    result = subprocess.run(
        [sys.executable, script_name],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print(f"✅ {test_name} PASSED")
        if result.stdout:
            # Print only the last few lines for brevity
            lines = result.stdout.split('\n')
            for line in lines[-5:]:
                if line.strip():
                    print(f"   {line}")
    else:
        print(f"❌ {test_name} FAILED")
        if result.stderr:
            print(f"   Error: {result.stderr[:500]}")
    
    return result.returncode

if __name__ == "__main__":
    print("🚀 RUNNING ALL TESTS")
    print("="*60)
    print("📱 You will receive Telegram notifications for each test!")
    print("="*60)
    
    # Check if test scripts exist in current directory or scripts folder
    script_dir = "scripts"
    
    tests = [
        ("Single Image", f"{script_dir}/test_single_image.py"),
        ("Carousel", f"{script_dir}/test_carousel.py"),
        ("Reel", f"{script_dir}/test_reel.py"),
    ]
    
    results = []
    for name, script in tests:
        if not os.path.exists(script):
            print(f"⚠️  Test file not found: {script}")
            continue
        result = run_test(name, script)
        results.append((name, result))
    
    # Summary
    print("\n" + "="*60)
    print("📊 TEST SUMMARY")
    print("="*60)
    for name, result in results:
        status = "✅ PASSED" if result == 0 else "❌ FAILED"
        print(f"  {name}: {status}")
    print("="*60)