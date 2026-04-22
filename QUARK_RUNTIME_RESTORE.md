## Runtime Restore

If you downloaded this runtime package from Quark:

1. Extract this folder to:
   - `D:\video_platform_release_windows_runtime`
   - or `C:\video_platform_release_windows_runtime`
2. Open the restored directory and run:
   - `verify_fixed_layout_runtime.cmd`
3. Start any launcher in:
   - `fixed_layout_programs\`

To restore the WSL source tree, use the GitHub backup repo:
- `https://github.com/qwe18358070112-sketch/video-platform-fixed-layout-backup`

Then run one of:

```bash
bash restore_source_snapshot.sh /home/lenovo/projects
```

or

```bat
restore_source_snapshot.cmd D:\restored_projects
```
