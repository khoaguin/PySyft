# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: proto/core/tensor/share_tensor.proto
"""Generated protocol buffer code."""
# third party
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import message as _message
from google.protobuf import reflection as _reflection
from google.protobuf import symbol_database as _symbol_database

# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


# syft absolute
from syft.proto.core.common import (
    recursive_serde_pb2 as proto_dot_core_dot_common_dot_recursive__serde__pb2,
)
from syft.proto.core.tensor import party_pb2 as proto_dot_core_dot_tensor_dot_party__pb2
from syft.proto.lib.numpy import array_pb2 as proto_dot_lib_dot_numpy_dot_array__pb2

DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(
    b"\n$proto/core/tensor/share_tensor.proto\x12\x10syft.core.tensor\x1a\x1bproto/lib/numpy/array.proto\x1a'proto/core/common/recursive_serde.proto\x1a\x1dproto/core/tensor/party.proto\"\xd9\x01\n\x0bShareTensor\x12\x32\n\x06tensor\x18\x01 \x01(\x0b\x32 .syft.core.common.RecursiveSerdeH\x00\x12+\n\x05\x61rray\x18\x02 \x01(\x0b\x32\x1a.syft.lib.numpy.NumpyProtoH\x00\x12\x0c\n\x04rank\x18\x03 \x01(\r\x12\x11\n\tseed_przs\x18\x04 \x01(\r\x12\x11\n\tring_size\x18\x05 \x01(\x0c\x12-\n\x0cparties_info\x18\x06 \x03(\x0b\x32\x17.syft.core.tensor.PartyB\x06\n\x04\x64\x61tab\x06proto3"
)


_SHARETENSOR = DESCRIPTOR.message_types_by_name["ShareTensor"]
ShareTensor = _reflection.GeneratedProtocolMessageType(
    "ShareTensor",
    (_message.Message,),
    {
        "DESCRIPTOR": _SHARETENSOR,
        "__module__": "proto.core.tensor.share_tensor_pb2"
        # @@protoc_insertion_point(class_scope:syft.core.tensor.ShareTensor)
    },
)
_sym_db.RegisterMessage(ShareTensor)

if _descriptor._USE_C_DESCRIPTORS == False:

    DESCRIPTOR._options = None
    _SHARETENSOR._serialized_start = 160
    _SHARETENSOR._serialized_end = 377
# @@protoc_insertion_point(module_scope)
