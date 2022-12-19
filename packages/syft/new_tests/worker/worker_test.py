# syft absolute
from syft.core.common.uid import UID
from syft.core.node.new.action_store import ActionStore
from syft.core.node.new.action_store import SIGNING_KEY_FOR
from syft.core.node.new.action_store import SyftSigningKey
from syft.core.node.new.action_store import SyftVerifyKey

# from syft.core.node.new.service_store import ServiceStore
from syft.core.node.worker import TestObject

# from syft.core.node.worker import Worker

test_signing_key_string = (
    "b7803e90a6f3f4330afbd943cef3451c716b338b17a9cf40a0a309bc38bc366d"
)

test_verify_key_string = (
    "08e5bcddfd55cdff0f7f6a62d63a43585734c6e7a17b2ffb3f3efe322c3cecc5"
)

test_signing_key_string_2 = (
    "8f4412396d3418d17c08a8f46592621a5d57e0daf1c93e2134c30f50d666801d"
)

test_verify_key_string_2 = (
    "833035a1c408e7f2176a0b0cd4ba0bc74da466456ea84f7ba4e28236e7e303ab"
)


def test_signing_key() -> None:
    # we should keep our representation in hex ASCII

    # first convert the string representation into a key
    test_signing_key = SyftSigningKey.from_string(test_signing_key_string)
    assert isinstance(test_signing_key, SyftSigningKey)

    # make sure it converts back to the same string
    assert str(test_signing_key) == test_signing_key_string

    # make a second one and verify that its equal
    test_signing_key_2 = SyftSigningKey.from_string(test_signing_key_string)
    assert test_signing_key == test_signing_key_2

    # get the derived verify key
    test_verify_key = test_signing_key.verify_key
    assert isinstance(test_verify_key, SyftVerifyKey)

    # make sure both types provide the verify key as a string
    assert test_verify_key_string == test_verify_key.verify
    assert test_verify_key_string == test_signing_key.verify

    # make sure that we don't print signing key but instead the verify key
    assert SIGNING_KEY_FOR in test_signing_key.__repr__()
    assert test_verify_key_string in test_signing_key.__repr__()

    # get another verify key from the same string and make sure its equal
    test_verify_key_2 = SyftVerifyKey.from_string(test_verify_key_string)
    assert test_verify_key == test_verify_key_2


def test_action_store() -> None:
    test_signing_key = SyftSigningKey.from_string(test_signing_key_string)
    action_store = ActionStore()
    uid = UID()
    test_object = TestObject(name="alice")
    set_result = action_store.set(
        uid=uid, credentials=test_signing_key, syft_object=test_object
    )
    assert set_result.is_ok()
    test_object_result = action_store.get(uid=uid, credentials=test_signing_key)
    assert test_object_result.is_ok()
    assert test_object == test_object_result.ok()

    test_verift_key_2 = SyftVerifyKey.from_string(test_verify_key_string_2)
    test_object_result_fail = action_store.get(uid=uid, credentials=test_verift_key_2)
    assert test_object_result_fail.is_err()
    assert "denied" in test_object_result_fail.err()


# def test_service_store() -> None:
#     test_signing_key = SyftSigningKey.from_string(test_signing_key_string)
#     service_store = ServiceStore()


# def test_worker()
# worker = Worker(
#     signing_key=test_signing_key,
#     action_store=action_store,
#     service_store=service_store,
# )
# assert False
