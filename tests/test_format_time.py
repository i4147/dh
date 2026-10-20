from dh import format_time
from loguru import logger


if __name__ == "__main__":
    for k in range(1, 60 * 60 * 24 * 30, 1000):
        logger.info(f"{k}: {format_time(k)}")
