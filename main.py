# -*- coding: utf-8 -*-

import sys

from utils import log
from config.settings import settings
from trade_manager import TradeManager

#
# Logger
#
logger = log.setup_custom_logger(settings.LOG_DIR, settings.LOG_NAME, settings.LOG_LEVEL)

#
# Main
#
if __name__ == "__main__":
    logger.info("Started Market Making Trading! Ver=" + settings.VERSION)

    tm = TradeManager(logger)

    # Try/except just keeps ctrl-c from printing an ugly stacktrace
    try:
        tm.init()
        tm.run_loop()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Ended Market Making Trading")
        sys.exit()
