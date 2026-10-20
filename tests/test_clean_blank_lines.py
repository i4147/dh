import os
from pathlib import Path
import tempfile
import unittest

from dh import clean_blank_lines
from loguru import logger


class TestCleanBlankLines(unittest.TestCase):
    def test_string_input_no_blank_lines(self) -> None:
        input_str = "Line 1\nLine 2\nLine 3"
        expected_output = "Line 1\nLine 2\nLine 3"
        logger.info(f"{input_str}\n{clean_blank_lines(input_str)}")
        self.assertEqual(clean_blank_lines(input_str), expected_output)

    def test_string_input_single_blank_lines(self) -> None:
        input_str = "Line 1\n\nLine 2\n\nLine 3"
        expected_output = "Line 1\n\nLine 2\n\nLine 3"
        logger.info(f"{input_str}\n{clean_blank_lines(input_str)}")
        self.assertEqual(clean_blank_lines(input_str), expected_output)

    def test_string_input_multiple_blank_lines(self) -> None:
        input_str = "Line 1\n\n\n\nLine 2\n\nLine 3\n\n\n"
        expected_output = "Line 1\n\nLine 2\n\nLine 3"
        logger.info(f"{input_str}\n{clean_blank_lines(input_str)}")
        self.assertEqual(clean_blank_lines(input_str), expected_output)

    def test_string_input_leading_trailing_blank_lines(self) -> None:
        input_str = "\n\n\nLine 1\nLine 2\n\n"
        expected_output = "\nLine 1\nLine 2"
        self.assertEqual(clean_blank_lines(input_str), expected_output)

    def test_string_input_empty_string(self) -> None:
        input_str = ""
        expected_output = "\n"
        logger.info(f"{input_str}\n{clean_blank_lines(input_str)}")
        self.assertEqual(clean_blank_lines(input_str), expected_output)

    def test_string_input_only_blank_lines(self) -> None:
        input_str = "\n\n\n\n"
        expected_output = "\n"
        logger.info(f"{input_str}\n{clean_blank_lines(input_str)}")
        self.assertEqual(clean_blank_lines(input_str), expected_output)

    def test_file_input_multiple_blank_lines(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".txt", encoding="utf-8") as tmp_file:
            file_path = Path(tmp_file.name)
            input_content = "File Line 1\n\n\nFile Line 2\n\nFile Line 3"
            tmp_file.write(input_content)
            tmp_file.flush()
            result_path_str = clean_blank_lines(file_path)
            result_path = Path(result_path_str)
            self.assertTrue(result_path.exists())
            self.assertEqual(
                result_path.read_text(encoding="utf-8"),
                "File Line 1\n\nFile Line 2\n\nFile Line 3\n",
            )
            self.assertEqual(result_path, file_path)
        if os.path.exists(file_path):
            os.remove(file_path)

    def test_file_input_no_blank_lines(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".txt", encoding="utf-8") as tmp_file:
            file_path = Path(tmp_file.name)
            input_content = "File Line 1\nFile Line 2\nFile Line 3"
            tmp_file.write(input_content)
            tmp_file.flush()
            result_path_str = clean_blank_lines(file_path)
            result_path = Path(result_path_str)
            self.assertEqual(
                result_path.read_text(encoding="utf-8"),
                "File Line 1\nFile Line 2\nFile Line 3\n",
            )
        if os.path.exists(file_path):
            os.remove(file_path)

    def test_invalid_input_type(self) -> None:
        with self.assertRaises(TypeError):
            clean_blank_lines(12345)


if __name__ == "__main__":
    unittest.main(argv=["first-arg-is-ignored"], exit=False)
