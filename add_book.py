import os

skipped_dirs = ['.github','venv','.git']

for dir_ in os.scandir():
    
    # only reading specific folders
    if dir_.is_dir() and dir_.name not in skipped_dirs:
        print(dir_.path,'\n\n')
