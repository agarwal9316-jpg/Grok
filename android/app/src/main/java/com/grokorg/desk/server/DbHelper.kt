package com.grokorg.desk.server

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper

class DbHelper(context: Context) :
    SQLiteOpenHelper(context, DB_NAME, null, DB_VERSION) {

    override fun onConfigure(db: SQLiteDatabase) {
        db.setForeignKeyConstraintsEnabled(true)
    }

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            """
            CREATE TABLE organisations (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL UNIQUE,
              description TEXT,
              created_at TEXT NOT NULL
            )
            """.trimIndent()
        )
        db.execSQL(
            """
            CREATE TABLE teams (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              organisation_id INTEGER NOT NULL,
              name TEXT NOT NULL,
              description TEXT,
              created_at TEXT NOT NULL,
              FOREIGN KEY(organisation_id) REFERENCES organisations(id) ON DELETE CASCADE
            )
            """.trimIndent()
        )
        db.execSQL(
            """
            CREATE TABLE agents (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              organisation_id INTEGER NOT NULL,
              team_id INTEGER,
              name TEXT NOT NULL,
              role TEXT NOT NULL,
              is_human INTEGER NOT NULL DEFAULT 0,
              system_prompt TEXT,
              created_at TEXT NOT NULL,
              FOREIGN KEY(organisation_id) REFERENCES organisations(id) ON DELETE CASCADE,
              FOREIGN KEY(team_id) REFERENCES teams(id) ON DELETE SET NULL
            )
            """.trimIndent()
        )
        db.execSQL(
            """
            CREATE TABLE channels (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              organisation_id INTEGER NOT NULL,
              name TEXT NOT NULL,
              description TEXT,
              created_at TEXT NOT NULL,
              FOREIGN KEY(organisation_id) REFERENCES organisations(id) ON DELETE CASCADE
            )
            """.trimIndent()
        )
        db.execSQL(
            """
            CREATE TABLE messages (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              channel_id INTEGER NOT NULL,
              agent_id INTEGER NOT NULL,
              content TEXT NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY(channel_id) REFERENCES channels(id) ON DELETE CASCADE,
              FOREIGN KEY(agent_id) REFERENCES agents(id) ON DELETE CASCADE
            )
            """.trimIndent()
        )
        db.execSQL(
            """
            CREATE TABLE tasks (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              organisation_id INTEGER NOT NULL,
              title TEXT NOT NULL,
              description TEXT,
              status TEXT NOT NULL DEFAULT 'pending',
              assignee_id INTEGER,
              channel_id INTEGER,
              parent_task_id INTEGER,
              result TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              FOREIGN KEY(organisation_id) REFERENCES organisations(id) ON DELETE CASCADE,
              FOREIGN KEY(assignee_id) REFERENCES agents(id) ON DELETE SET NULL,
              FOREIGN KEY(channel_id) REFERENCES channels(id) ON DELETE SET NULL,
              FOREIGN KEY(parent_task_id) REFERENCES tasks(id) ON DELETE SET NULL
            )
            """.trimIndent()
        )
        db.execSQL(
            """
            CREATE TABLE app_settings (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            )
            """.trimIndent()
        )
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        // Fresh schema for v1.2 standalone — wipe and recreate
        db.execSQL("DROP TABLE IF EXISTS messages")
        db.execSQL("DROP TABLE IF EXISTS tasks")
        db.execSQL("DROP TABLE IF EXISTS agents")
        db.execSQL("DROP TABLE IF EXISTS channels")
        db.execSQL("DROP TABLE IF EXISTS teams")
        db.execSQL("DROP TABLE IF EXISTS organisations")
        db.execSQL("DROP TABLE IF EXISTS app_settings")
        onCreate(db)
    }

    companion object {
        const val DB_NAME = "grok_org_os.db"
        const val DB_VERSION = 1
    }
}
