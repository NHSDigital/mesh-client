from unittest import TestCase, main, skip

from requests import HTTPError

import mesh_client


class EndpointConnectivityTest(TestCase):
    @skip("This test needs N3 connectivity, talks to real endpoints, and is Python 3 only, so don't run it by default")
    def test_connectivity(self):
        for key, endpoint in mesh_client.__dict__.items():
            if key.endswith("_ENDPOINT") and not key.startswith("LOCAL_") and "_OPENTEST_" not in key:
                with self.subTest(key):
                    print("Testing", key)
                    with self.assertRaises(HTTPError) as cm:
                        client = mesh_client.MeshClient(endpoint, "BADUSERNAME", "BADPASSWORD")
                        client.handshake()
                    self.assertEqual(cm.exception.response.status_code, 400)


if __name__ == "__main__":
    main()
