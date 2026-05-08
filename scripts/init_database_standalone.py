#!/usr/bin/env python3
"""
Script standalone para inicializar DB con Docker Compose

NO requiere imports del proyecto - funciona standalone

Uso:
    python scripts/init_database_standalone.py
"""

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import secrets
import uuid


# ============================================
# CONFIGURACIÓN - Edita según tu docker-compose.yml
# ============================================

DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'datalink',
    'user': 'dev',
    'password': 'dev123'  # ← Cambia esto según tu docker-compose.yml
}


def main():
    """Inicializa la base de datos"""
    
    print("🚀 DataLink V1 - Inicialización de Base de Datos")
    print("=" * 60)
    
    try:
        # Conectar a PostgreSQL
        print("\n🔌 Conectando a PostgreSQL en Docker...")
        conn = psycopg2.connect(**DB_CONFIG)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        
        print("✅ Conectado exitosamente")
        
        # Crear ENUM para plan
        print("\n📋 Creando tipo ENUM para planes...")
        cur.execute("""
            DO $$ BEGIN
                CREATE TYPE user_plan AS ENUM ('FREE', 'STARTER', 'PRO', 'BUSINESS');
            EXCEPTION
                WHEN duplicate_object THEN 
                    RAISE NOTICE 'tipo user_plan ya existe, saltando...';
            END $$;
        """)
        print("✅ Tipo user_plan configurado")
        
        # Crear tabla users
        print("\n👤 Creando tabla users...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id VARCHAR(36) PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                api_key VARCHAR(64) UNIQUE NOT NULL,
                plan user_plan NOT NULL DEFAULT 'FREE',
                files_processed_this_month INTEGER NOT NULL DEFAULT 0,
                files_processed_total INTEGER NOT NULL DEFAULT 0,
                last_reset_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                stripe_customer_id VARCHAR(255),
                stripe_subscription_id VARCHAR(255),
                is_active BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE
            )
        """)
        
        # Índices para users
        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_api_key ON users(api_key)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_plan ON users(plan)")
        
        print("✅ Tabla users creada con índices")
        
        # Crear tabla plan_limits
        print("\n💰 Creando tabla plan_limits...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS plan_limits (
                plan VARCHAR(20) PRIMARY KEY,
                files_per_month INTEGER NOT NULL,
                max_file_size_mb INTEGER NOT NULL,
                max_records_per_file INTEGER NOT NULL,
                num_presets INTEGER NOT NULL,
                custom_filters_allowed BOOLEAN NOT NULL,
                api_keys_count INTEGER NOT NULL,
                requests_per_hour INTEGER NOT NULL,
                sla_uptime FLOAT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)
        print("✅ Tabla plan_limits creada")
        
        # Seed plan_limits
        print("\n📊 Configurando límites de planes...")
        
        plans = [
            ('FREE', 10, 10, 200000, 2, False, 0, 10, None),
            ('STARTER', 100, 100, 2000000, 5, True, 1, 100, None),
            ('PRO', 500, 500, 10000000, 5, True, 3, 500, 99.50),
            ('BUSINESS', -1, 2000, 40000000, 5, True, 10, 2000, 99.90)
        ]
        
        for plan_data in plans:
            cur.execute("""
                INSERT INTO plan_limits 
                (plan, files_per_month, max_file_size_mb, max_records_per_file, 
                 num_presets, custom_filters_allowed, api_keys_count, 
                 requests_per_hour, sla_uptime)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (plan) DO UPDATE SET
                    files_per_month = EXCLUDED.files_per_month,
                    max_file_size_mb = EXCLUDED.max_file_size_mb,
                    max_records_per_file = EXCLUDED.max_records_per_file,
                    num_presets = EXCLUDED.num_presets,
                    custom_filters_allowed = EXCLUDED.custom_filters_allowed,
                    api_keys_count = EXCLUDED.api_keys_count,
                    requests_per_hour = EXCLUDED.requests_per_hour,
                    sla_uptime = EXCLUDED.sla_uptime
            """, plan_data)
            
            print(f"  ✅ Plan {plan_data[0]}: {plan_data[1]} files/mes, {plan_data[2]}MB max")
        
        # Actualizar tabla processing_jobs
        print("\n🔧 Actualizando tabla processing_jobs...")
        
        # Verificar si la tabla existe
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'processing_jobs'
            )
        """)
        
        if cur.fetchone()[0]:
            cur.execute("""
                ALTER TABLE processing_jobs 
                ADD COLUMN IF NOT EXISTS user_id VARCHAR(36)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_jobs_user_id 
                ON processing_jobs(user_id)
            """)
            print("✅ Columna user_id agregada a processing_jobs")
        else:
            print("⚠️  Tabla processing_jobs no existe aún (se creará después)")
        
        # Crear usuario de prueba
        print("\n🧪 Creando usuario de prueba...")
        
        test_user_id = str(uuid.uuid4())
        test_api_key = secrets.token_urlsafe(32)
        test_email = 'test@datalink.com'
        
        # Verificar si el usuario ya existe
        cur.execute("SELECT api_key, plan FROM users WHERE email = %s", (test_email,))
        existing = cur.fetchone()
        
        if existing:
            print(f"✅ Usuario de prueba ya existe:")
            print(f"   Email: {test_email}")
            print(f"   API Key: {existing[0]}")
            print(f"   Plan: {existing[1]}")
        else:
            cur.execute("""
                INSERT INTO users (id, email, api_key, plan)
                VALUES (%s, %s, %s, %s)
            """, (test_user_id, test_email, test_api_key, 'FREE'))
            
            print(f"✅ Usuario de prueba creado:")
            print(f"   Email: {test_email}")
            print(f"   API Key: {test_api_key}")
            print(f"   Plan: FREE")
            
            print(f"\n📝 GUARDA ESTE API KEY:")
            print(f"   {test_api_key}")
        
        # Resumen final
        print("\n" + "=" * 60)
        print("✅ Inicialización completada exitosamente!")
        print("=" * 60)
        
        print("\n📋 Resumen:")
        
        # Contar usuarios
        cur.execute("SELECT COUNT(*) FROM users")
        user_count = cur.fetchone()[0]
        
        # Contar planes
        cur.execute("SELECT COUNT(*) FROM plan_limits")
        plan_count = cur.fetchone()[0]
        
        print(f"  • {user_count} usuario(s) en la base de datos")
        print(f"  • {plan_count} planes configurados")
        
        print("\n🚀 Siguiente paso:")
        print("   1. Guarda el API Key del usuario de prueba")
        print("   2. Reinicia tu API: uvicorn app.main:app --reload")
        print("   3. Prueba con: curl -H 'X-API-Key: <tu_key>' http://localhost:8000/api/v1/usage")
        
        cur.close()
        conn.close()
        
        return True
        
    except psycopg2.Error as e:
        print(f"\n❌ Error de PostgreSQL:")
        print(f"   {e}")
        print("\n💡 Verifica que:")
        print("   1. Docker Compose está corriendo: docker-compose up -d")
        print("   2. PostgreSQL está UP: docker-compose ps")
        print("   3. Las credenciales en DB_CONFIG son correctas")
        return False
    
    except Exception as e:
        print(f"\n❌ Error inesperado:")
        print(f"   {e}")
        return False


if __name__ == "__main__":
    success = main()
    
    if not success:
        print("\n❌ Inicialización falló")
        exit(1)
    else:
        print("\n✅ Todo listo para usar DataLink V1!")
        exit(0)