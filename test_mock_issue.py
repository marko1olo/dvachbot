import unittest

def run_tests():
    import tests.test_main
    import tests.test_site_importer

    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(tests.test_site_importer)
    runner = unittest.TextTestRunner()
    runner.run(suite)

if __name__ == "__main__":
    run_tests()
