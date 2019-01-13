"""
The TrustChain Community is the first step in an incremental approach in building a new reputation system.
This reputation system builds a tamper proof interaction history contained in a chain data-structure.
Every node has a chain and these chains intertwine by blocks shared by chains.
"""
from __future__ import absolute_import

import hashlib
import os
from binascii import unhexlify
from datetime import datetime
from functools import wraps
from threading import RLock
import json

from twisted.internet.defer import succeed

from pyipv8 import NewCommunityCreatedEvent
from pyipv8.ipv8.keyvault.crypto import ECCrypto
from .block import BobChainBlock
from .database import BobChainDB
from .settings import BobChainSettings
from ..trustchain.block import ANY_COUNTERPARTY_PK, ValidationResult
from ...community import Community
from ...peer import Peer

receive_block_lock = RLock()

# Static block_type, using home_property instead of property to not use the same name as a property type in python
BLOCK_TYPE_PROPERTY = b'HOME_PROPERTY'

# PROPERTY_TO_DETAILS_KEY = {}  # Maps property hash to (property details, keypair)

# try:
#     with open('property_to_key_mappings.json', 'r') as file:
#         json_file = json.load(file)
#         for property in json_file:
#             with open("keys/" + property[1] + ".pem", 'r') as key:
#                 key_content = key.read()
#                 PROPERTY_TO_DETAILS_KEY[property[1]] = (property[0], ECCrypto().key_from_private_bin(key_content))
# except IOError:
#     with open('property_to_key_mappings.json', 'w') as file:
#         json.dump([], file)
# PUBLIC_KEY = [b'0' * 74,
#               b'4jpvnlpbnesusvlkxh7d34u8mfq1gxc0la4usd54oooeulraw7dwv72d4nfn7czhaulen9fjbn',
#               b'xtkbp3zv88ruj2k63rizkelbhzg58gzcp09od1pt867ksn8i5xrn2zafqjfzua8hhdzhgp7376',
#               b'vvt6ng10p1w50jg9rmyy10tqqmmemrw59uf0ifa22odjg9hfuxoxx8ngv2apd7w6rlzh3cjfbu',
#               b'3f0xw1jtns6heuk478h58k3dburaeig6s2bt5vo5oz3bz2dfvel85g0edt3qsmgn06npr0we5s',
#               b'ev46dkjzfrc7vjywv7i3h0qcxpquuj9v5xit9z0lshzz53t6exb3vblrtnthupulthstdi7svh']


def synchronized(f):
    """
    Due to database inconsistencies, we can't allow multiple threads to handle a received_half_block at the same time.
    """

    @wraps(f)
    def wrapper(self, *args, **kwargs):
        with receive_block_lock:
            return f(self, *args, **kwargs)

    return wrapper


class BOBChainCommunity(Community):
    bobChainCommunity = None

    # TODO figure this out
    # Took the trustchain community values...
    master_peer = Peer(unhexlify("3081a7301006072a8648ce3d020106052b8104002703819200040672297aa47c7bb2648ba0385275bc"
                                 "8ade5aedc3677a615f5f9ca83b9b28c75e543342875f7f353bbf74baff7e3dae895ee9c9a9f80df023"
                                 "dbfb72362426b50ce35549e6f0e0a319015a2fd425e2e34c92a3fb33b26929bcabb73e14f63684129b"
                                 "66f0373ca425015cc9fad75b267de0cfb46ed798796058b23e12fc4c42ce9868f1eb7d59cc2023c039"
                                 "14175ebb9703"))

    DB_CLASS = BobChainDB
    DB_NAME = 'bobchain'

    def __init__(self, *args, **kwargs):

        # initialize the database:
        working_directory = kwargs.pop('working_directory', '')
        db_name = kwargs.pop('db_name', self.DB_NAME)
        self.settings = kwargs.pop('settings', BobChainSettings())

        super(BOBChainCommunity, self).__init__(*args)
        self.persistence = self.DB_CLASS(working_directory, db_name)
        self.country = kwargs["country"]
        self.state = kwargs["state"]
        self.city = kwargs["city"]
        self.street = kwargs["street"]
        self.number = kwargs["number"]
        NewCommunityCreatedEvent.event(self)

    def book_apartment(self, property_public_key):
        # if block.is_genesis:
        #     continue
        # start_day = block.transaction["start_day"].split("-")
        # end_day = block.transaction["end_day"].split("-")
        # start_day_tuple = (int(start_day[0]), int(start_day[1]), int(start_day[2]))
        # end_day_tuple = (int(end_day[0]), int(end_day[1]), int(end_day[2]))
        # current_day = datetime.now()
        # current_day_tuple = (current_day.year, current_day.month, current_day.day)
        # if start_day_tuple <= current_day_tuple <= end_day_tuple:
        #     print "Overbooking!"
        #     return
        self.create_link_bob(
            property_public_key=property_public_key,
            transaction=
            {
                b"start_day": datetime.now().strftime("%Y-%m-%d"),  # 2000-01-31
                b"end_day": "2999-01-01",
            }
        )
        print "Booked apartment"

    def get_apartments(self):
        result = set()
        for block in self.persistence.get_blocks_with_type(BLOCK_TYPE_PROPERTY):
            if not block.is_genesis:
                continue
            property = (block.public_key, block.transaction["city"])
            if property not in result:
                result.add(property)
        return result

    def publish_license(self, country, state, city, street, number):
        self.create_genesis_block(BLOCK_TYPE_PROPERTY, {
            "country": country,
            "state": state,
            "city": city,
            "street": street,
            "number": number,
        })

    def create_genesis_block(self, block_type, property):
        """
        Create a genesis block without any initial counterparty to sign.

        :param block_type: The type of the block to be constructed, as a string
        :param transaction: A string describing the interaction in this block
        :param public_key: A string of 74 characters that is a public key
        :return: A deferred that fires with a (block, None) tuple
        """
        assert property is None or isinstance(property, dict), "Property should be a dictionary"

        property_key = ECCrypto().generate_key(u"medium")
        property_id = hashlib.sha224(json.dumps(property)).hexdigest()
        PROPERTY_TO_DETAILS_KEY[property_id] = (property, property_key)

        with open('property_to_key_mappings.json', 'w') as file:
            l = []
            for property_id, details_key in PROPERTY_TO_DETAILS_KEY.items():
                l.append([details_key[0], property_id])
            json.dump(l, file)

        with open("keys/" + str(property_id) + ".pem", 'w') as f:
            f.write(PROPERTY_TO_DETAILS_KEY[property_id][1].key_to_bin())

        source_block = self.get_block_class(block_type).create(block_type, property, self.persistence,
                                                               public_key=PROPERTY_TO_DETAILS_KEY[property_id][1].pub().key_to_bin())

        # TODO self.my_peer.key is not the right input
        source_block.sign(PROPERTY_TO_DETAILS_KEY[property_id][1])

        if not self.persistence.contains(source_block):
            self.persistence.add_block(source_block)

            return succeed((source_block, None))

    def create_link_bob(self, property_public_key, transaction):
        print "Source block's public key", property_public_key
        # print "Source block is genesis: ", source_block.is_genesis

        source_block = self.persistence.get_latest(property_public_key)

        self.create_link(source=source_block, block_type=BLOCK_TYPE_PROPERTY, transaction=transaction)

        print "Number of linked blocks:", len(self.persistence.get_all_linked(source_block))

    # This function will remove all the created blocks in the bobchain community
    def remove_all_created_blocks(self):
        print "Going to remove all blocks"

        blocks = self.persistence.get_all_blocks()
        print "Number of blocks found: ", len(blocks)

        for block in blocks:
            self.persistence.remove_block(block)
        blocks = self.persistence.get_all_blocks()

        if len(blocks) == 0:
            print "All blocks have succesfully been removed"
        else:
            print "Not all blocks have been removed, number of blocks remaining: ", len(blocks)

    def print_blocks(self):
        blocks = self.persistence.get_all_blocks()
        i = 0
        for block in blocks:
            print "block number: ", i, " is_genesis: ", block.is_genesis
            print "transaction", block.transaction
            print "has id: ", block.block_id
            print "linked_block_id: ", block.linked_block_id
            i += 1

    def started(self):

        def wrapper_create_and_remove_blocks():

            # self.create_genesis_block()
            #
            # self.create_genesis_block()
            #
            # self.create_genesis_block()
            #
            # self.create_link_bob()

            # j = 0
            # for i in range(0, 5):
            #     create_block(j)
            #     j += 1

            self.print_blocks()

            self.remove_all_created_blocks()

        BOBChainCommunity.bobChainCommunity = self
        # We register a Twisted task with this overlay.
        # This makes sure that the task ends when this overlay is unloaded.
        # We call the 'print_peers' function every 5.0 seconds, starting now.
        # self.register_task("print_peers", LoopingCall(print_peers)).start(5.0, True)
        # self.register_task("print_blocks", LoopingCall(wrapper_create_and_remove_blocks)).start(5.0, True)

    @synchronized
    def sign_block(self, peer=None, public_key=None, block_type=BLOCK_TYPE_PROPERTY, transaction=None, linked=None,
                   additional_info=None):
        """
        Create, sign, persist and send a block signed message
        :param peer: The peer with whom you have interacted, as a IPv8 peer
        :param public_key: The public key of the other party you transact with
        :param block_type: The type of the block to be constructed, as a string
        :param transaction: A string describing the interaction in this block
        :param linked: The block that the requester is asking us to sign
        :param additional_info: Stores additional information, on the transaction
        """

        # TODO:
        # Should add assertion checks below that makes sense for the BOBChain
        # check the trustchain/community sign_block() to get an idea of what are good assertions
        assert transaction is None or isinstance(transaction, dict), "Transaction should be a dictionary"
        assert additional_info is None or isinstance(additional_info, dict), "Additional info should be a dictionary"

        # TODO:
        # Check below should be implemented, this check makes sure that the latest block in the chain
        # can be validated, otherwise the database needs to be sanitized
        # self.persistence_integrity_check()

        # TODO:
        # Add linkage logic
        # if linked and linked.link_public_key != ANY_COUNTERPARTY_PK:
        #     block_type = linked.type

        # TODO
        # Fix input for the get_block_class, this should not be a static string
        block = self.get_block_class(b'HOME_PROPERTY').create(block_type, transaction, self.persistence,
                                                              public_key=public_key, link=linked,
                                                              additional_info=transaction)

        block.sign(self.my_peer.key)

        # TODO
        # Write validation logic

        # Add block to database:
        if not self.persistence.contains(block):
            self.persistence.add_block(block)
            # self.notify_listeners(block)

        # This is a source block with no counterparty
        if not peer and public_key == ANY_COUNTERPARTY_PK:
            # TODO figure this out
            # if self.settings.broadcast_blocks:
            #     self.send_block(block)
            return succeed((block, None))

        # TODO
        # No Counter party is ever needed, see how we need to handle this
        # If there is a counterparty to sign, we send it
        # self.send_block(block, address=peer.address)

        # TODO
        # Find logic when we broadcast the block
        # Probably when we think it is validated
        # We broadcast the block in the network if we initiated a transaction
        # if self.settings.broadcast_blocks and not linked:
        #     self.send_block(block)

        # Self signed block, this seems to be the situation
        if peer == self.my_peer:
            # We created a self-signed block
            # TODO figure out how to send this
            # if self.settings.broadcast_blocks:
            #     self.send_block(block)

            return succeed((block, None)) if public_key == ANY_COUNTERPARTY_PK else succeed((block, linked))
        # elif not linked:
        #     # We keep track of this outstanding sign request.
        #     sign_deferred = Deferred()
        #     self.request_cache.add(HalfBlockSignCache(self, block, sign_deferred, peer.address))
        #     return sign_deferred
        # else:
        #     # We return a deferred that fires immediately with both half blocks.
        #     if self.settings.broadcast_blocks:
        #         self.send_block_pair(linked, block)
        #
        #     return succeed((linked, block))

    def create_link(self, source, block_type, transaction, public_key=None):
        """
        Create a Link Block to a source block

        :param source: The source block which had no initial counterpary to sign
        :param block_type: The type of the block to be constructed, as a string
        :param additional_info: a dictionary with supplementary information concerning the transaction
        :param public_key: The public key of the counterparty (usually of the source's owner)
        :return: None
        """
        public_key = source.public_key if public_key is None else public_key

        return self.sign_block(self.my_peer, transaction=transaction, linked=source, public_key=public_key, block_type=block_type)

    def validate_persist_block(self, block):
        """
        Validate a block and if it's valid, persist it. Return the validation result.
        :param block: The block to validate and persist.
        :return: [ValidationResult]
        """
        validation = block.validate(self.persistence)
        if validation[0] == ValidationResult.invalid:
            pass
        elif not self.persistence.contains(block):
            self.persistence.add_block(block)
            self.notify_listeners(block)

        return validation

    def get_block_class(self, block_type):
        """
        Get the block class for a specific block type.
        """
        assert block_type == BLOCK_TYPE_PROPERTY, "Wrong type of block is being created"

        return BobChainBlock

    def persistence_integrity_check(self):
        """
        Perform an integrity check of our own chain. Recover it if needed.
        """
        block = self.persistence.get_latest(self.my_peer.public_key.key_to_bin())
        if not block:
            return

        # TODO
        # validation = self.validate_persist_block(block)
        # if validation[0] != ValidationResult.partial_next and validation[0] != ValidationResult.valid:
        #     self.logger.error("Our chain did not validate. Result %s", repr(validation))
        #     self.sanitize_database()
