import aiosqlite
import datetime

class DatabaseUser:
    def __init__(self, db_name='user.db'):
        self.db_name = db_name  # Initialize the database path

    async def init_db(self):
        async with aiosqlite.connect(self.db_name) as db:
            # Users table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    nation_id TEXT NOT NULL,
                    credits INTEGER DEFAULT 0
                )
            ''')
            await db.commit()
            print("Users table created successfully")

            # Companies table without total_shares
            await db.execute('''
                CREATE TABLE IF NOT EXISTS companies (
                    company_name TEXT PRIMARY KEY,
                    share_price REAL NOT NULL,
                    user_id TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            await db.commit()
            print("Companies table created successfully")

            # Total Shares table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS total_shares (
                    company_name TEXT NOT NULL,
                    total_shares INTEGER NOT NULL,
                    PRIMARY KEY (company_name),
                    FOREIGN KEY (company_name) REFERENCES companies (company_name)
                )
            ''')
            await db.commit()
            print("Total Shares table created successfully")

            # Share price history table
            await db.execute('''    
                CREATE TABLE IF NOT EXISTS share_price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_name TEXT NOT NULL,
                    date TEXT NOT NULL,
                    time TEXT NOT NULL,
                    share_price REAL NOT NULL
                )
            ''')
            await db.commit()
            print("Share price history table created successfully")

            # User shares table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS user_shares (
                    user_id TEXT NOT NULL,
                    company_name TEXT NOT NULL,
                    shares INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, company_name),
                    FOREIGN KEY (user_id) REFERENCES users (user_id),
                    FOREIGN KEY (company_name) REFERENCES companies (company_name)
                )
            ''')
            await db.commit()
            print("User shares table created successfully")
            await db.execute('''
                CREATE TABLE IF NOT EXISTS registered_shares (
                    company_name TEXT NOT NULL,
                    registered_share INTEGER NOT NULL,
                    PRIMARY KEY (company_name),
                    FOREIGN KEY (company_name) REFERENCES companies (company_name)
                )
            ''')
            await db.commit()
            print("Registered Shares table created successfully")
        
            await db.execute('''
            CREATE TABLE IF NOT EXISTS trades (
            trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER NOT NULL,
            company_name TEXT NOT NULL,
            shares_available INTEGER NOT NULL,
            price_per_share REAL NOT NULL,
            to_user_id INTEGER
            )
            ''')
            await db.commit()
            print("Trades table created successfully")

    async def add_user(self, user_id: str, nation_id: str):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute(
                "INSERT OR REPLACE INTO users (user_id, nation_id) VALUES (?, ?)",
                (user_id, nation_id)
            )
            await db.commit()

    async def get_user_data_by_user_id(self, user_id: str):
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute("SELECT nation_id FROM users WHERE user_id = ?", (user_id,)) as cursor:
                result = await cursor.fetchone()
                return result[0] if result else None

    async def get_user_data_by_nation_id(self, nation_id: str):
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute("SELECT user_id FROM users WHERE nation_id = ?", (nation_id,)) as cursor:
                result = await cursor.fetchone()
                return result[0] if result else None

    async def add_credits(self, user_id: str, amount: int):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("""
                UPDATE users
                SET credits = credits + ?
                WHERE user_id = ?
            """, (amount, user_id))
            await db.commit()

    async def get_user_credits(self, user_id: str):
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute("""
                SELECT credits FROM users WHERE user_id = ?
            """, (user_id,)) as cursor:
                result = await cursor.fetchone()
                return result[0] if result else None

    async def add_company(self, company_name: str, share_price: float, total_shares: int, user_id: str):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute(
                "INSERT INTO companies (company_name, share_price, user_id) VALUES (?, ?, ?)",
                (company_name, share_price, user_id)
            )
            await db.commit()

            await db.execute(
                "INSERT INTO total_shares (company_name, total_shares) VALUES (?, ?)",
                (company_name, total_shares)
            )
            await db.commit()

    async def get_company_by_name(self, company_name: str):
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute("""
                SELECT c.company_name, c.share_price, ts.total_shares, c.user_id
                FROM companies c
                LEFT JOIN total_shares ts ON c.company_name = ts.company_name
                WHERE c.company_name = ?
            """, (company_name,)) as cursor:
                result = await cursor.fetchone()
                return result  # This will be a tuple (company_name, share_price, total_shares, user_id)

    async def get_company_data_by_user_id(self, user_id: str):
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute("""
                SELECT c.company_name, c.share_price, ts.total_shares
                FROM companies c
                LEFT JOIN total_shares ts ON c.company_name = ts.company_name
                WHERE c.user_id = ?
            """, (user_id,)) as cursor:
                result = await cursor.fetchall()
                return result

    async def get_company_price(self, share_price: str):
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute("SELECT share_price FROM companies WHERE share_price = ?", (share_price,)) as cursor:
                result = await cursor.fetchone()
                return result[0] if result else None

    async def get_all_companies(self):
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute("""
                SELECT c.company_name, c.share_price, ts.total_shares, c.user_id
                FROM companies c
                LEFT JOIN total_shares ts ON c.company_name = ts.company_name
            """) as cursor:
                result = await cursor.fetchall()
                return result

    async def update_user_credits_after_purchase(self, user_id: str, amount: int):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("""
                UPDATE users
                SET credits = credits - ?
                WHERE user_id = ?
            """, (amount, user_id))
            await db.commit()

    async def update_company_share_price(self, company_name: str, new_share_price: float):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("""
                UPDATE companies
                SET share_price = ?
                WHERE company_name = ?
            """, (new_share_price, company_name))
            await db.commit()
    async def store_share_price_history(self, company_name: str, date: str, time: str, share_price: float):
        async with aiosqlite.connect(self.db_name) as db:
            # First check if the record already exists
            async with db.execute("""
                SELECT * FROM share_price_history WHERE company_name = ? AND date = ? AND time = ?
            """, (company_name, date, time)) as cursor:
                result = await cursor.fetchone()
        
            if result is None:  # If no record exists, insert the new one
                await db.execute("""
                    INSERT INTO share_price_history (company_name, date, time, share_price)
                    VALUES (?, ?, ?, ?)
                """, (company_name, date, time, share_price))
                await db.commit()

    async def get_share_price_history(self, company_name: str, period: str):
        today = datetime.datetime.now()
        if period == "1h":
            start_time = today - datetime.timedelta(hours=1)
            interval = datetime.timedelta(minutes=5)
        elif period == "12h":
            start_time = today - datetime.timedelta(hours=12)
            interval = datetime.timedelta(minutes=60)
        elif period == "1d":
            start_time = today - datetime.timedelta(days=1)
            interval = datetime.timedelta(minutes=120)
        elif period == "3d":
            start_time = today - datetime.timedelta(days=3)
            interval = datetime.timedelta(minutes=720)
        elif period == "7d":
            start_time = today - datetime.timedelta(days=7)
            interval = datetime.timedelta(minutes=1440)
        else:
            return None

        start_time = start_time.strftime("%Y-%m-%d %H:%M:%S")
    
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute(
                "SELECT date, time, share_price FROM share_price_history WHERE company_name = ? AND datetime(date || ' ' || time) >= ? ORDER BY date, time",
                (company_name, start_time)
            ) as cursor:
                result = await cursor.fetchall()
                return result

    async def get_company_name(self, company_name: str):
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute("SELECT share_price FROM companies WHERE company_name = ?", (company_name,)) as cursor:
                result = await cursor.fetchone()
                if result:
                    return result[0]  # Return the actual share price
                return None

    async def get_user_shares(self, user_id: str, company_name: str) -> int:
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute("""
                SELECT shares FROM user_shares WHERE user_id = ? AND company_name = ?
            """, (user_id, company_name)) as cursor:
                result = await cursor.fetchone()
                return result[0] if result else 0

    async def update_user_shares(self, user_id: str, company_name: str, shares_change: int):
        async with aiosqlite.connect(self.db_name) as db:
            current_shares = await self.get_user_shares(user_id, company_name)
            new_shares = current_shares + shares_change

            if new_shares < 0:
                raise ValueError("User cannot have negative shares.")

            await db.execute("""
                INSERT INTO user_shares (user_id, company_name, shares)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, company_name) DO UPDATE SET shares=excluded.shares
            """, (user_id, company_name, new_shares))
            await db.commit()

    async def remove_company(self, company_name: str):
        async with aiosqlite.connect(self.db_name) as db:
            # Remove from user_shares table first to prevent foreign key constraint issues
            await db.execute("DELETE FROM user_shares WHERE company_name = ?", (company_name,))
            await db.commit()
        
            # Remove from share_price_history table
            await db.execute("DELETE FROM share_price_history WHERE company_name = ?", (company_name,))
            await db.commit()

            # Finally, remove from companies table
            await db.execute("DELETE FROM companies WHERE company_name = ?", (company_name,))
            await db.commit()

            # Remove from total_shares table
            await db.execute("DELETE FROM total_shares WHERE company_name = ?", (company_name,))
            await db.commit()

        print(f"Company {company_name} has been removed from the database.")
        
    async def update_company_details(self, company_name: str, new_share_price: float, new_total_shares: int):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("""
                UPDATE companies
                SET share_price = ?
                WHERE company_name = ?
            """, (new_share_price, company_name))
            await db.commit()

            await db.execute("""
                UPDATE total_shares
                SET total_shares = ?
                WHERE company_name = ?
            """, (new_total_shares, company_name))
            await db.commit()
            
    async def add_shares(self, company_name: str, registered_share: int):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("""
            INSERT INTO registered_shares (company_name, registered_share)
            VALUES (?, ?)
            ON CONFLICT(company_name) DO UPDATE SET registered_share = excluded.registered_share
            """, (company_name, registered_share))
            await db.commit()

            
    async def get_shares(self, company_name: str):
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute("""
            SELECT registered_share FROM registered_shares WHERE company_name = ?
            """, (company_name,)) as cursor:
                result = await cursor.fetchone()
                return result[0] if result else None
            
    async def get_all_trades(self):
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute("""
            SELECT trade_id, seller_id, company_name, shares_available, price_per_share
            FROM trades
            """) as cursor:
                result = await cursor.fetchall()
                return result
    async def create_trade(self, company_name: str, seller_id: int, num_shares: int, price_per_share: float, to_user_id: int = None):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("""
            INSERT INTO trades (company_name, seller_id, shares_available, price_per_share, to_user_id)
            VALUES (?, ?, ?, ?, ?)
            """, (company_name, seller_id, num_shares, price_per_share, to_user_id))
            await db.commit()
            
    async def delete_trade(self, trade_id: int):
        async with aiosqlite.connect(self.db_name) as db:
            # Remove the trade from the trades table
            await db.execute("DELETE FROM trades WHERE trade_id = ?", (trade_id,))
            await db.commit()
    async def get_trade(self, trade_id: int):
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute("""
            SELECT trade_id, seller_id, company_name, shares_available, price_per_share, to_user_id
            FROM trades
            WHERE trade_id = ?
            """, (trade_id,)) as cursor:
                result = await cursor.fetchone()
                if result:
                    return {
                    "trade_id": result[0],
                    "seller_id": result[1],
                    "company_name": result[2],
                    "shares_available": result[3],
                    "price_per_share": result[4],
                    "to_user_id": result[5]
                    }
                return None
