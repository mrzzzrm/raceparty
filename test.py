import unittest
import main

class CreateCupsTest(unittest.TestCase):
    def test_create_cups2(self):
        for num_players in range(2, 10):
            for num_cups in range(int(num_players / 4), 10):
                print(num_players, num_cups)
                with self.subTest(num_players=num_players, num_cups=num_cups):
                    main.create_cups2(range(0, num_players), num_cups, 4)

if __name__ == '__main__':
    unittest.main()