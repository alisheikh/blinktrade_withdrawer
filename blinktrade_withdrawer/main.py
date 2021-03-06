import os
import argparse
import getpass
import json

from binascii import unhexlify
from simplecrypt import decrypt

import ConfigParser
from appdirs import site_config_dir

from urlparse import urlparse

from model import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from twisted.internet import reactor, ssl

from autobahn.twisted.websocket import WebSocketClientFactory
from twisted.internet.protocol import ReconnectingClientFactory
from blinktrade_withdrawal_protocol import BlinktradeWithdrawalProtocol

class BlinkTradeClientFactory(WebSocketClientFactory, ReconnectingClientFactory):
    protocol = BlinktradeWithdrawalProtocol
    def clientConnectionFailed(self, connector, reason):
        print("Client connection failed .. retrying ..")
        self.retry(connector)

    def clientConnectionLost(self, connector, reason):
        print("Client connection lost .. retrying ..")
        self.retry(connector)


def main():
  parser = argparse.ArgumentParser(description="Process blinktrade withdrawals requests")

  parser.add_argument('-c',
                      "--config",
                      action="store",
                      dest="config",
                      help='Configuration file', type=str)

  arguments = parser.parse_args()

  candidates = [ os.path.join(site_config_dir('blinktrade'), 'blinktrade_withdrawer.ini'),
                 os.path.expanduser('~/.blinktrade/blinktrade_withdrawer.ini')]
  if arguments.config:
    candidates.append(arguments.config)

  config = ConfigParser.SafeConfigParser()
  config.read( candidates )

  password = getpass.getpass('password: ')


  blinktrade_port = 443
  should_connect_on_ssl = True
  blinktrade_url = urlparse( config.get("blinktrade", "webscoket_url"))
  if  blinktrade_url.port is None and blinktrade_url.scheme == 'ws':
    should_connect_on_ssl = False
    blinktrade_port = 80

  db_engine = config.get("database", "sqlalchemy_engine") + ':///' +\
              os.path.expanduser(config.get("database", "sqlalchemy_connection_string"))
  engine = create_engine(db_engine, echo=config.getboolean('database', 'sqlalchmey_verbose'))
  Base.metadata.create_all(engine)

  factory = BlinkTradeClientFactory(blinktrade_url.geturl())
  factory.db_session                  = scoped_session(sessionmaker(bind=engine))
  factory.verbose                     = config.getboolean("blinktrade", "verbose")
  factory.blinktrade_broker_id        = config.get("blinktrade", "broker_id")
  factory.blinktrade_user             = decrypt(password, unhexlify(config.get("blinktrade", "user")))
  factory.blinktrade_password         = decrypt(password, unhexlify(config.get("blinktrade", "password")))
  factory.currencies                  = json.loads(config.get("blinktrade", "currencies"))
  factory.methods                     = json.loads(config.get("blinktrade", "methods"))
  factory.blocked_accounts            = json.loads(config.get("blinktrade", "blocked_accounts"))

  if config.has_section('blockchain_info'):
    from blockchain_info import BlockchainInfoWithdrawalProtocol
    factory.blockchain_guid             = decrypt(password, unhexlify(config.get("blockchain_info", "guid")))
    factory.blockchain_main_password    = decrypt(password, unhexlify(config.get("blockchain_info", "main_password")))
    factory.blockchain_second_password  = decrypt(password, unhexlify(config.get("blockchain_info", "second_password")))
    factory.from_address                = config.get("blockchain_info", "from_address")
    factory.note                        = config.get("blockchain_info", "note")
    factory.protocol = BlockchainInfoWithdrawalProtocol

  if config.has_section('mailer'):
    from mailer_protocol import MailerWithdrawalProtocol
    factory.mandrill_apikey             = config.get("mailer", "mandrill_apikey")
    factory.mandrill_template_name      = config.get("mailer", "template_name")
    factory.mandrill_from_email         = config.get("mailer", "from_email")
    factory.mandrill_from_name          = config.get("mailer", "from_name")
    factory.mandrill_to_email           = config.get("mailer", "to_email")
    factory.mandrill_to_name            = config.get("mailer", "to_name")
    factory.mandrill_website            = config.get("mailer", "website")
    factory.protocol = MailerWithdrawalProtocol

  if should_connect_on_ssl:
    reactor.connectSSL( blinktrade_url.netloc ,  blinktrade_port , factory, ssl.ClientContextFactory() )
  else:
    reactor.connectTCP(blinktrade_url.netloc ,  blinktrade_port , factory )

  reactor.run()


if __name__ == '__main__':
  main()
