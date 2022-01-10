# -*- coding: utf-8 -*-

import logging
from datetime import datetime


def setup_custom_logger(log_dir, log_name, log_level):
    formatter = logging.Formatter(fmt='%(asctime)s - %(levelname)s - %(message)s')

    # file handler
    now = datetime.now()
    log_file = log_dir + '/' + log_name + '_' + now.strftime("%Y_%m_%d") + '.log'
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)

    # stream handler
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    # logger
    logger = logging.getLogger(log_name)
    logger.setLevel(log_level)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

    return logger
