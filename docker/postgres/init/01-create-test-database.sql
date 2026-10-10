-- Runs once, when the PostgreSQL volume is first initialised.
-- The backend integration suite owns this database and resets it freely;
-- the reset helpers refuse to operate on any database whose name does not end in "_test".
CREATE DATABASE qa_commerce_test;
