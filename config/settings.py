# -*- coding: utf-8 -*-

from __future__ import absolute_import
from utils.dotdict import DotDict
from config import constants as constants

# global configuration
settings = {}

# convert constants to dictionary notation
settings.update(vars(constants))

# convert dictionary to dot notation
settings = DotDict(settings)
