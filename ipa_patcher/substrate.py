# -*- coding: utf-8 -*-
import os, shutil, logging, sys
log = logging.getLogger(__name__)

def inject_substrate(app_dir, script_dir, substrate_source=None):
    substrate_path = os.path.join(app_dir, "libsubstrate.dylib")
    if substrate_source is None:
        src = os.path.join(script_dir, "libsubstrate.dylib")
        if not os.path.isfile(src):
            log.error("Не найден libsubstrate.dylib. Положите его в папку со скриптом или укажите путь.")
            sys.exit(1)
    else:
        src = substrate_source
        if not os.path.isfile(src):
            log.error("Указанный файл субстрата не найден: %s", src)
            sys.exit(1)
    shutil.copy2(src, substrate_path)
    os.chmod(substrate_path, 0o755)
    log.info("Субстрат скопирован: %s", substrate_path)
    return substrate_path