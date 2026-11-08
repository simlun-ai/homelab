"""PUBLIC fixture: stdlib HMAC HKDF + PyCryptodome 3.23.0 AES-GCM; no real keys."""

VECTOR = {
    "node": "11111111-2222-4333-8444-555555555555",
    "key_id": "homelab/v1/trust/kms/public-fixture/r1",
    "key_hex": "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f",
    "plaintext_hex": "202122232425262728292a2b2c2d2e2f303132333435363738393a3b3c3d3e3f",
    "salt_hex": "404142434445464748494a4b4c4d4e4f505152535455565758595a5b5c5d5e5f",
    "nonce_hex": "606162636465666768696a6b",
    "info_hex": "686f6d656c61622d6b6d732d76310031313131313131312d323232322d343333332d383434342d35353535353535353535353500686f6d656c61622f76312f74727573742f6b6d732f7075626c69632d666978747572652f7231",
    "derived_key_hex": "8d796628d5220f90dabd8b7223075c75f78e71491bf089c6c8b8e455dd660c00",
    "aad": '{"encoding":"raw-32","format":"homelab-kms-v1","key_id":"homelab/v1/trust/kms/public-fixture/r1","node_uuid":"11111111-2222-4333-8444-555555555555","nonce":"YGFiY2RlZmdoaWpr","salt":"QEFCQ0RFRkdISUpLTE1OT1BRUlNUVVZXWFlaW1xdXl8="}',
    "envelope": '{"ciphertext":"4Txl3LupJm7kgHksudQobix52xtl8geZ1agH4gUgfIpl0YnXQPilkGFTA7M1RLnP","encoding":"raw-32","format":"homelab-kms-v1","key_id":"homelab/v1/trust/kms/public-fixture/r1","node_uuid":"11111111-2222-4333-8444-555555555555","nonce":"YGFiY2RlZmdoaWpr","salt":"QEFCQ0RFRkdISUpLTE1OT1BRUlNUVVZXWFlaW1xdXl8="}',
}
