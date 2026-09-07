with open("inventory/views.py", "r") as f:
    lines = f.readlines()
with open("inventory/views.py", "w") as f:
    f.writelines(lines[:44] + lines[136:])

with open("inventory/dashboard_views.py", "r") as f:
    lines = f.readlines()
with open("inventory/dashboard_views.py", "w") as f:
    f.writelines(lines[:51] + lines[81:])
