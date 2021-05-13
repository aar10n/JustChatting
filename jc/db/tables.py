# Mysql Table Creation Queries

EMOTES_TABLE = '''
  CREATE TABLE IF NOT EXISTS `emotes` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `organization_id` INT,
    `name` VARCHAR(255),
    `url` VARCHAR(255),
    `created_at` DATETIME,
    `updated_at` DATETIME,
    PRIMARY KEY (`id`)
  );
'''

TABLES = [
  EMOTES_TABLE
]
