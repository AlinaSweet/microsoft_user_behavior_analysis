"""Exercise grouped stratification with repeated historical purchase pairs."""

import unittest

import duckdb

from user_behavior_analysis.dao.sampling_repository import assign_pair_groups


class GroupedSplitTests(unittest.TestCase):
    """Use the real assignment query to check held-out pair separation."""

    def test_repeat_pair_is_assigned_once_and_stratified_by_any_positive(self) -> None:
        """Keep all cutoffs of a pair together and stratify on its maximum label."""
        with duckdb.connect() as connection:
            connection.execute(
                "CREATE VIEW natural_samples AS SELECT "
                + "CAST(i//5 AS VARCHAR) AS user_id,"
                + "CAST(i AS VARCHAR) AS item_id,cutoff,"
                + "(i%5=0 AND cutoff=2)::INTEGER AS target "
                + "FROM range(100) pairs(i), range(3) anchors(cutoff)"
            )
            assign_pair_groups(connection, seed=12)
            counts = connection.execute(
                "SELECT stratum,"
                + "COUNT(*) FILTER(WHERE split='train'),"
                + "COUNT(*) FILTER(WHERE split='validation'),"
                + "COUNT(*) FILTER(WHERE split='test') "
                + "FROM pair_assignment GROUP BY stratum ORDER BY stratum"
            ).fetchall()
            overlap = connection.execute(
                "SELECT COUNT(*) FROM (SELECT user_id,item_id "
                + "FROM natural_samples JOIN pair_assignment USING(user_id,item_id) "
                + "GROUP BY user_id,item_id "
                + "HAVING COUNT(DISTINCT split)>1 OR COUNT(*)<>3)"
            ).fetchone()
        self.assertEqual(counts, [(0, 56, 16, 8), (1, 14, 4, 2)])
        self.assertEqual(overlap, (0,))


if __name__ == "__main__":
    unittest.main()
