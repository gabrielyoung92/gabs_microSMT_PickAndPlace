import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('feeder_bus',Path(__file__).resolve().parents[1]/'tools'/'feeder_bus.py')
bus=importlib.util.module_from_spec(spec);spec.loader.exec_module(bus)
class ClientTests(unittest.TestCase):
    def test_known_wire_vector(self):
        # Cross-check against the C suite's fixed header/transaction layout.
        frame=bus.encode(7,1,0x12345678,b'wire test')
        self.assertEqual(frame.hex(),'a55a010700017856341277697265207465737400000098c4')
    def test_reply_matching_and_crc(self):
        import binascii
        request=bus.encode(7,2,123)
        reply=bytearray(request);reply[3]=0;reply[4]=7;reply[5]|=0x80
        reply[22:]=binascii.crc_hqx(reply[:22],0xffff).to_bytes(2,'little')
        self.assertEqual(bus.decode_reply(reply,request),bytes(12))
        reply[6]^=1
        with self.assertRaises(ValueError):bus.decode_reply(reply,request)
        reply[22:]=binascii.crc_hqx(reply[:22],0xffff).to_bytes(2,'little')
        with self.assertRaises(ValueError):bus.decode_reply(reply,request)
    def test_bad_addresses(self):
        for address in [0,248,255]:
            with self.assertRaises(ValueError):bus.encode(address,1,0)
    def test_tcp_fragmented_reply(self):
        request=bus.encode(7,4,123)
        reply=b'RX '+request.hex().encode()+b'\n'
        with patch.object(bus.socket,'create_connection') as connect:
            stream=connect.return_value.__enter__.return_value
            stream.recv.side_effect=[reply[:1],reply[1:17],reply[17:]]
            self.assertEqual(bus.exchange_tcp('example.invalid',4242,request),request)
            connect.assert_called_once_with(('example.invalid',4242),timeout=2)
            stream.sendall.assert_called_once_with(b'XFER '+request.hex().upper().encode()+b'\n')
    def test_tcp_errors_do_not_retry(self):
        for chunks,error in [([b'ERR BUSY\n'],RuntimeError),([b'RX A5',b''],RuntimeError),
                             ([b'x'*128],ValueError),([b'garbage\n'],ValueError),
                             ([b'RX XX\n'],ValueError)]:
            with self.subTest(chunks=chunks),patch.object(bus.socket,'create_connection') as connect:
                stream=connect.return_value.__enter__.return_value
                stream.recv.side_effect=chunks
                with self.assertRaises(error):bus.exchange_tcp('example.invalid',4242,b'')
                self.assertEqual(connect.call_count,1)
                self.assertEqual(stream.sendall.call_count,1)
if __name__=='__main__':unittest.main()
