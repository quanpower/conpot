# Copyright (C) 2013  Lukas Rist <glaslos@gmail.com>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.


import logging
import json

import gevent
from gevent.queue import Queue

from lxml import etree

from modules import snmp_command_responder, modbus_server

import config
from modules.loggers import sqlite_log, feeder

logger = logging.getLogger()


def log_worker(log_queue):
    if config.sqlite_enabled:
        sqlite_logger = sqlite_log.SQLiteLogger()
    if config.hpfriends_enabled:
        friends_feeder = feeder.HPFriendsLogger()

    while True:
        event = log_queue.get()
        assert 'data_type' in event
        assert 'timestamp' in event

        if config.hpfriends_enabled:
            friends_feeder.log(json.dumps(event))

        if config.sqlite_enabled:
            sqlite_logger.log(event)


def create_snmp_server(template, log_queue):
    dom = etree.parse(template)
    mibs = dom.xpath('//conpot_template/snmp/mibs/*')
    #only enable snmp server if we have configuration items
    if not mibs:
        snmp_server = None
    else:
        snmp_server = snmp_command_responder.CommandResponder(log_queue)

    for mib in mibs:
        mib_name = mib.attrib['name']
        for symbol in mib:
            symbol_name = symbol.attrib['name']
            value = symbol.xpath('./value/text()')[0]
            snmp_server.register(mib_name, symbol_name, value)
    return snmp_server


if __name__ == "__main__":

    root_logger = logging.getLogger()

    console_log = logging.StreamHandler()
    console_log.setLevel(logging.DEBUG)
    console_log.setFormatter(logging.Formatter('%(asctime)-15s %(message)s'))
    root_logger.addHandler(console_log)

    servers = []

    log_queue = Queue()
    gevent.spawn(log_worker, log_queue)

    logger.setLevel(logging.DEBUG)
    modbus_daemon = modbus_server.ModbusServer('templates/default.xml', log_queue).get_server(config.modbus_host,
                                                                                              config.modbus_port)
    servers.append(gevent.spawn(modbus_daemon.serve_forever))

    snmp_server = create_snmp_server('templates/default.xml', log_queue)
    if snmp_server:
        logger.info('SNMP server started.')
        servers.append(gevent.spawn(snmp_server.serve_forever))

    gevent.joinall(servers)
