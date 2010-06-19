.. |SP| replace:: :class:`~procedure.StoredProcedure`
.. |RS| replace:: :class:`~stored_procedures.sql.SQL`


Documentation of the Stored Procedures Module
=============================================

.. module:: stored_procedures

This module provides a wrapper around stored procedures for MySQL and generic raw SQL expressions in django. The former is handled by |SP|, the latter by |RS|.

Raw SQL
=======

There are situations in which raw SQL queries are necessary, when the ORM as provided by django is too restrictive to solve the problem at hand. Unfortunately, using raw SQL opens up a new batch of potential pitfalls. Below a small example of things that can go wrong, followed by a possible solution using |RS|. The example is too small to be useful, but one familiar with large raw expressions might see the added value in the safity provided by |RS|.

Before
------------

Suppose you have the model as below in the application `locations`,::

    class Office(models.Model):
        name = models.CharField(max_length = 100)

and the following model in `administration`.::

    class Employee(models.Model):
        name    = models.CharField(max_length = 100)
        office  = models.ForeignKey('locations.Office')

Now suppose you want to count the number of employees per office.[#naive1]_ This can be done by means of the following code::

    from django.db import connection

    cursor = connection.cursor()
    cursor.execute("""SELECT office.name, COUNT(*)
        FROM
                employee
            ,   office
        WHERE
            office.id = employee.office_id
        GROUP BY
            office.id""")
    print cursor.fetchall()
    cursor.close()

Notice that many things are wrong with the fragment above.
* you have no way of knowing whether the table `Employee` has database column `employee` (by default, it will not have this name at all);
* the reference to `Office` from `Employee` might have a different database column than `office_id`;
* some exceptions might be thrown
* a warning may occur, and it may be written to stderr.

After
------------
Using |RS|, one can simply write::

    print SQL("""SELECT e.[locations.Office.name], COUNT(*)
        FROM
                [administration.Employee] as e
            ,   [locations.Office] as o
        WHERE
                e.[administration.Employee.office] = o.[locations.Office.pk]
        GROUP BY
            [locations.Office.pk]""")()

This performs the very same query. Instead of having to guess names in the database corresponding to  models, they are automatically inferred. Moreover, they are auto-escaped whenever needed and Warnings are suppressed by default.

.. rubric:: Footnotes

.. [#naive] Note that this example is not a very good motivator, as it can be solved satisfactory wholly within the ORM. See it merely as an illustration of the kind of problems one runs into when writing custom queries, not as an actual usecase.

The SQL Class
-------------
.. autoclass:: stored_procedures.sql.SQL
    :members: __call__, content, __unicode__, __str__

.. note:: Even though |RS| is discussed first in the documentation, it was constructed much later and used more scarcely than |SP|. It thus might have more bugs than its size would lead to believe.

Stored Procedure
==============================

When writing stored procedures, one is faced with the same difficulties as when writing raw SQL. Moreover, many things can go wrong when executing a stored procedure. It might be the case that you forgot to save the stored procedure to the database, or that you entered an incorrect number of arguments. One has to ensure that the stored procedure that you wrote down is actually stored in the database. In order to make this a little bit easier, one can use |SP|.


A Small Example
---------------

Suppose you have a shop, and want to allow orders only of items that have a sufficiently large stock. This example is too easy to show the full potential of stored procedures, but is does nicely illustrate the use of |SP|. Consider the models for the app `shop` ::

    class OrderManager(models.Manager):
        placeOrder = StoredProcedure(filename = 'shop/placeOrder.sql', results = True)

    class Stock(models.Model):
        name    = models.CharField(max_length = 100)
        amount  = models.PositiveIntegerField()

    class Order(models.Model):
        product = models.ForeignKey(Stock)
        amount  = models.PositiveIntegerField()

        objects = OrderManager()


The stored procedure that handles these orders is stored in the file 'placeOrder.sql', which contains the following.

.. code-block:: mysql

    CREATE PROCEDURE  placeOrder
        (
                IN orderedAmount INT
            ,   IN product CHAR(100)
        )
        MODIFIES SQL DATA
    BEGIN
        DECLARE stockID INT;
        DECLARE stockAmount INT

        SELECT
                [shop.Stock.pk]
            ,   [shop.Stock.amount]
        INTO
                stockID
            ,   stockAmount
        FROM
            [shop.Stock]
        WHERE
            [shop.Stock.name] = product;

        IF stockAmount >= orderedAmount THEN
            INSERT INTO
                [shop.Order]
                (
                        [shop.Order.product]
                    ,   [shop.Order.amount]
                )
            VALUES
                (
                        stockID
                    ,   orderedAmount
                );

            SET newOrderID = LAST_INSERT_ID();

            UPDATE
                [shop.Stock]
            SET
                [shop.Stock.amount] = [shop.Stock.amount] - orderedAmount;
            WHERE
                [shop.Stock.pk] = stockID;

            SELECT stockAmount, newOrderID;
        ELSE
            SELECT 0,0;
        END IF;
    END;

    When one now execute the code::

    print Order.objects.placeOrder(product = "Tomato", orderedAmount = 10)

    the stored procedure is called and the results are printed. Note that this call is made using keyword argument; |SP| ensures that these come back in the right order. Were one to execute::

    print Order.objects.placeOrder(products = "Tomatoes", orderedAmount = 10)

    then :exp:`~exceptions.InvalidArgument` would be raised. When printing this exception, you immediately see the incorrect argument you used (`arguments`) and the ones that were available (`argument`, `orderedAmount`)

.. autoclass:: procedure.StoredProcedure
    :members: __call__, resetProcedure, readProcedure, renderProcedure, send_to_database, name, filename, arguments, hasResults, call

Indices and tables
==================
* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

