-- hw01: نمونه تمرین پایگاه داده

# number 1
-- نمایش دانشجویان با نمره >= 18
SELECT id, name, grade
FROM students
WHERE grade >= 18;

# number 2
-- تعداد دانشجویان با نمره >= 18
SELECT COUNT(*) AS student_count
FROM students
WHERE grade >= 18;

# number 3
-- نام دانشجویان با نمره < 18
SELECT name
FROM students
WHERE grade < 18;
