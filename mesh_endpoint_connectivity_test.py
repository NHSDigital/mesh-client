from unittest import TestCase, main, skip
import mesh_client
from requests import HTTPError


class EndpointConnectivityTest(TestCase):
    @skip("This test needs N3 connectivity, talks to real endpoints, and is Python 3 only, so don't run it by default")
    def test_connectivity(self):
        for key, endpoint in list(mesh_client.__dict__.items()):
            if key.endswith('_ENDPOINT') and not key.startswith('LOCAL_') and not '_OPENTEST_' in key:
                with self.subTest(key):
                    print("Testing", key)
                    with self.assertRaises(HTTPError) as cm:
                        client = mesh_client.MeshClient(endpoint, 'BADUSERNAME', 'BADPASSWORD')
                        client.handshake()
                    self.assertEqual(cm.exception.response.status_code, 400)


if __name__ == '__main__':
    main()
