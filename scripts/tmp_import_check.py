import importlib
mods = ['backend.models.sd','backend.pipeline']
for m in mods:
    try:
        importlib.invalidate_caches()
        mod = importlib.import_module(m)
        print('import ok:', m)
    except Exception as e:
        print('import ERROR for', m)
        import traceback
        traceback.print_exc()
