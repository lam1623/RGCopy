#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# copy_with_rgcopy.py
import imp
from threading import Thread

rgcopy = imp.load_source('rgcopy', '/opt/RGCopy/rgcopy.py')
#rgcopy = imp.load_source('rgcopy', '/media/reisy/home/reisy/Documents/desarrollo_propio/RGCopy/rgcopy.py')


main = rgcopy.RGCopy()
if main.lines:
	thread = Thread(target=main.run_process)
	thread.start()
	main.show()
