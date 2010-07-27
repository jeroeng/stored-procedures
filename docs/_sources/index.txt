.. |SP| replace:: :class:`~procedure.StoredProcedure`
.. |RS| replace:: :class:`~stored_procedures.sql.SQL`
.. _MySQL: http://dev.mysql.com/doc/
.. _django: http://www.djangoproject.com/
.. |SPs| replace:: stored procedures
.. _SPs: http://dev.mysql.com/doc/refman/5.5/en/stored-programs-views.html
.. |MyPython| replace:: MySQL-Python
.. _MyPython: http://mysql-python.sourceforge.net/MySQLdb.html

Documentation of the Stored Procedures Module
=============================================

.. module:: stored_procedures

This module provides a wrapper around |SPs|_ for |MyPython|_ and generic raw SQL expressions in django_. The former is handled by |SP|, the latter by |RS|.

Stored Procedure
==============================

When writing |SPs|_, one is faced with the same difficulties as when writing raw SQL (see :ref:`raw-SQL`). Moreover, many things can go wrong when executing a stored procedure. It might be the case that you forgot to save the stored procedure to the database, or that you entered an incorrect number of arguments. One has to ensure that the stored procedure in the code is actually the one stored in the database. In order to make this a little bit easier, one can use |SP|.


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


When one now executes the code::

    print Order.objects.placeOrder(product = "Tomato", orderedAmount = 10)

the stored procedure is called and the results are printed. Note that this call is made using keyword arguments; |SP| ensures that these come back in the right order. Were one to execute::

    print Order.objects.placeOrder(products = "Tomatoes", orderedAmount = 10)

then :exc:`~exceptions.InvalidArgument` would be raised. When printing this exception, you immediately see the incorrect argument you used (`arguments`) and the ones that were available (`argument`, `orderedAmount`).

Features
--------

Using Model Names
^^^^^^^^^^^^^^^^^
As described above, simply refer to tables, columns or primary keys respectively using [app.table], [app.table.column], [app.table.pk].

Automatically Push to Database
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Database migrations, as provided for instance by `South <http://south.aeracode.org/docs/>`_, are the ideal moment to push stored procedures to the database server. This is the default behavious. Each instance of |SP| automatically is bound to the `post_migrate <http://south.aeracode.org/docs/signals.html#post-migrate>`_ signal. After a migration, the procedure is deleted from the database and re-created.

Catching Exceptions and Warnings
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
When executing a stored procedure, many things could go wrong. It is often useful to know this as early as possible, with as much information as possible. Every risky operation in |SP| is wrapped in a try-catch block, yielding a new exception that is enriched with information about the procedure and hints towards solving it. Moreover, |MyPython|_ can yield warnings which are directly printed to `sys.stderr`. This is inconvenient in some situations, |SP| allows you to automatically suppress these warnings, or raise them as exceptions by setting a flag.

Re-order Arguments
^^^^^^^^^^^^^^^^^^
There is no need to remember the order in which the arguments were given in the stored procedure. When calling |SP|, the (usual) arguments are seen as the first few arguments to the underlying stored procedure, and the keyword arguments can be provided in any order. Mistakes like nameclashes, invalid arguments, too few arguments are handled gracefully by the exceptions :exc:`TypeError`, :exc:`~exceptions.InvalidArgument` and :exc:`~exceptions.InsufficientArguments` respectively.

Automatically infer Arguments
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Due to the above feature one needs to know the arguments to a specific stored procedure. These arguments can be provided by hand, but usually, they can be inferred automatically. [#autoinfer]_ If this is not possible, you will be notified of this by means of the exception :exc:`~exceptions.ArgumentsIrretrievableException`.

In order to be able to parse the procedure, it first has to be loaded from file. The file containing the procedure must be in the location as specified by filename. In a django project, it is often useful to specify the following in settings.py::

    import os.path, functools
    SITE_ROOT = os.path.realpath(os.path.dirname(__file__))
    IN_SITE_ROOT = functools.partial(os.path.join, SITE_ROOT)


When IN_SITE_ROOT is available, it will be used to make the filename absolute. When the file can not be found, :exc:`~exceptions.FileDoesNotWorkException` is raised.

.. rubric:: Footnotes

.. [#autoinfer] The `syntax <http://dev.mysql.com/doc/refman/5.5/en/create-procedure.html>`_ of stored procedures in MySQL_ is quite lax. Automatic 'parsing' of the procedure is only possible when each argument is annotated by `IN`, `OUT` or `INOUT`.

Reference
---------

.. autoclass:: procedure.StoredProcedure
    :members: __call__, resetProcedure, readProcedure, renderProcedure, send_to_database, name, filename, arguments, hasResults, call

.. _raw-SQL:

Raw SQL
=======

There are situations in which raw SQL queries are necessary, when the ORM as provided by django is too restrictive to solve the problem at hand. Unfortunately, using raw SQL opens up a new batch of potential pitfalls. Below a small example of things that can go wrong, followed by a possible solution using |RS|. The example is too small to be useful, but one familiar with large raw expressions might see the added value in the safety provided by |RS|.

Before
------------

Suppose you have the model as below in the application `locations`::

    class Office(models.Model):
        name = models.CharField(max_length = 100)

and the following model in `administration`.::

    class Employee(models.Model):
        name    = models.CharField(max_length = 100)
        office  = models.ForeignKey('locations.Office')

Now suppose you want to count the number of employees per office. [#naive1]_ This can be done by means of the following code::

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

Notice that many things are wrong with the fragment above:

* you have no way of knowing whether the table `Employee` has database column `employee` (by default, it will not have this name at all);
* the reference to `Office` from `Employee` might have a different database column than `office_id`;
* some exceptions might be thrown;
* a warning may occur, and it may be written to `sys.stderr`. [#warnings]_

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

This performs the very same query. Instead of having to guess names in the database corresponding to  models, they are automatically inferred. Moreover, they are auto-escaped whenever needed and warnings are suppressed by default.

.. rubric:: Footnotes

.. [#naive1] Note that this example is not a very good motivator, as it can be solved satisfactory wholly within the ORM. See it merely as an illustration of the kind of problems one runs into when writing custom queries, not as an actual usecase.
.. [#warnings] |MyPython|_ handles warnings using :exc:`Warning`, see its `documentation <http://mysql-python.sourceforge.net/MySQLdb.html>`_ for more details. 

Reference
---------
.. autoclass:: stored_procedures.sql.SQL
    :members: __call__, content, __unicode__, __str__

.. note:: Even though |RS| is discussed first in the documentation, it was constructed much later and used more scarcely than |SP|. It thus might have more bugs than its size would lead to believe.

Exceptions
==========

.. automodule:: stored_procedures.exceptions
    :members:
    :undoc-members:

Library
=======

.. automodule:: stored_procedures.library
    :members: StoredProcedureLibary, registerProcedure, resetProcedures,reset, library
    :undoc-members:

Indices and tables
==================
* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

