import sys
import os
import asyncio
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

def main():
    rc = 0
    try:
        from fastapi.testclient import TestClient
        from main import app

        print("=" * 70)
        print("FastAPI 接口功能回归测试 (TestClient 进程内验证)")
        print("=" * 70)

        with TestClient(app) as client:
            # ---- 1. /health ----
            print("\n[1/3] GET /health")
            r = client.get("/health")
            assert r.status_code == 200, f"状态码={r.status_code}"
            body = r.json()
            assert body["status"] == "healthy"
            assert body["architecture"] == "modbus_receiver -> cfd_simulator -> air_quality_analyzer -> alarm_mqtt"
            assert "redis_pubsub" in body["bus"]
            assert len(body["configs"]) == 3
            print(f"  [OK] status={body['status']}, version={body['version']}")
            print(f"  [OK] 架构: {body['architecture']}")
            print(f"  [OK] 总线: {body['bus']}")
            print(f"  [OK] 配置文件: {body['configs']}")

            # ---- 2. GET / ----
            print("\n[2/3] GET / (index.html 静态页)")
            r = client.get("/")
            if r.status_code == 200:
                content = r.text
                assert "长信宫灯" in content or "gongdeng" in content.lower() or "canvas" in content.lower() or "three" in content.lower(), "首页内容异常"
                print(f"  [OK] 首页 HTML ({len(content)} 字节)")
            else:
                print(f"  [INFO] 首页非200: status={r.status_code} (可能frontend目录不存在)")

            # ---- 3. POST /api/sensor/data ----
            print("\n[3/3] POST /api/sensor/data (核心管线触发)")
            payload = {
                "lamp_id": 1,
                "oil_consumption": 2.1,
                "flue_temperature": 148.0,
                "flue_velocity": 0.52,
                "indoor_pm25": 72.0,
                "oil_level": 390,
                "ambient_temperature": 23.8,
                "ambient_humidity": 52.0,
                "fuel_type": "sesame_oil",
                "air_change_rate": 1.0,
                "outdoor_pm25": 28.0,
            }
            r = client.post("/api/sensor/data", json=payload)
            assert r.status_code == 200, f"状态码={r.status_code}, body={r.text[:300]}"
            body = r.json()
            print(f"  [OK] 状态码 200")

            print(f"\n  --- 返回字段解析 ---")
            assert "validation" in body, "缺少 validation"
            v = body["validation"]
            print(f"  [OK] validation.passed = {v.get('passed')}")
            if v.get('errors'):
                print(f"  [INFO] 校验错误: {v['errors']}")

            # 检查 CFD 仿真结果
            if "flue_simulation" in body and body["flue_simulation"]:
                fs = body["flue_simulation"]
                for k in ["reynolds_number", "outlet_temperature", "settling_efficiency", "flow_regime"]:
                    assert k in fs, f"CFD结果缺少 {k}"
                print(f"  [OK] flue_simulation: Re={fs['reynolds_number']:.0f}, "
                      f"T_out={fs['outlet_temperature']:.1f}C, "
                      f"settle={fs['settling_efficiency']*100:.1f}% (如果是0-1) / {fs['settling_efficiency']:.1f}% (如果是百分比), "
                      f"flow={fs['flow_regime']}")
            else:
                print(f"  [INFO] flue_simulation: 未同步返回 (管线异步处理中)")

            # 检查空气质量结果
            if "air_quality" in body and body["air_quality"]:
                aq = body["air_quality"]
                keys = list(aq.keys())[:8]
                print(f"  [OK] air_quality 字段: {keys}")
                if "aqi_level" in aq:
                    print(f"       AQI等级: {aq['aqi_level']}")
            else:
                print(f"  [INFO] air_quality: 未同步返回 (管线异步处理中)")

            # 检查告警
            if "alerts" in body and isinstance(body["alerts"], list):
                alerts = body["alerts"]
                print(f"  [OK] alerts: {len(alerts)} 条")
                for a in alerts[:3]:
                    print(f"       - {a.get('alert_type')} / {a.get('severity')}: {a.get('message')}")
            else:
                print(f"  [INFO] alerts: 列表未直接返回")

            print(f"\n  --- 完整返回字段 ---")
            print(f"  {list(body.keys())}")

        print("\n" + "=" * 70)
        print("API 功能回归测试 PASS")
        print("=" * 70)

    except AssertionError as e:
        print(f"\n[FAIL] 断言失败: {e}")
        import traceback
        traceback.print_exc()
        rc = 1
    except Exception as e:
        print(f"\n[FATAL] 测试崩溃: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        rc = 1

    return rc


if __name__ == "__main__":
    sys.exit(main())
