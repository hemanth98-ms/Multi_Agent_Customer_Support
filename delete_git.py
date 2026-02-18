import shutil
import os
import stat

def remove_readonly(func, path, excinfo):
    os.chmod(path, stat.S_IWRITE)
    func(path)

try:
    if os.path.exists('.git'):
        print("Removing .git...")
        shutil.rmtree('.git', onerror=remove_readonly)
        print(".git removed.")
    else:
        print(".git not found.")
        
    if os.path.exists('.gitignore'):
        os.remove('.gitignore')
        print(".gitignore removed.")
except Exception as e:
    print(f"Error: {e}")
