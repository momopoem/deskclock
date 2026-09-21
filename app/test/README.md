# 物理センサーの診断

本体の `app/services/sensor_service.py` を使い、配線から測定値取得まで確認します。
各スクリプトは既定で有効な測定値を1回取得して終了します。無限ループではありません。

| 対象 | 個別スクリプト | 測定項目 |
|---|---|---|
| BME280 | `bme280_test.py` | 温度・湿度・気圧 |
| SCD40 | `scd40_test.py` | CO₂・温度・湿度・CRC |
| SHT20 | `sht20_test.py` | 温度・湿度 |
| AHT21 | `aht21_test.py` | 温度・湿度（raw I²C） |
| ENS160 | `ens160_test.py` | 状態・AQI・TVOC・eCO₂ |
| BH1750 | `bh1750_test.py` | 照度 |
| HC-SR501 | `pir_test.py` / `sr501_test.py` | GPIOの現在値 |
| カメラ | `camera_test.py` | フレーム取得・画像サイズ |

## 実機での一括診断

本体と診断プロセスのI²Cロックは共有されないため、実機診断時はサービスを停止してください。
次のサブシェルは、もともと起動していたサービスを終了時に再開します。

```bash
cd ~/deskclock
(
  was_active=0
  if systemctl --user is-active --quiet deskclock.service; then
    was_active=1
    systemctl --user stop deskclock.service || exit 1
  fi
  trap 'if [ "$was_active" = 1 ]; then systemctl --user start deskclock.service; fi' EXIT
  ./venv/bin/python app/test/sensor_diag.py --sensor all --samples 2 --timeout 30 --output /tmp/deskclock-sensors.json
)
```

個別診断も同じくサービス停止中に実行します。

```bash
./venv/bin/python app/test/bme280_test.py --samples 3 --timeout 30
./venv/bin/python app/test/camera_test.py --device 0 --samples 3
./venv/bin/python app/test/pir_test.py --samples 100 --timeout 40
```

`--timeout` はセンサーごとの制限秒数です。通信自体が停止した場合も、親プロセスが
制限時間に2秒の終了猶予を加えて子プロセスを終了します。全体は各センサーを順番に診断し、
1種類が失敗しても残りを実行します。標準出力はセンサーごとのJSON、`--output` は集約JSONです。
終了コードは全件成功 `0`、失敗・準備未完了 `1`、引数エラー `2`、中断 `130`。

バス・アドレス・GPIO・有効フラグ・測定間隔・温度補正は本体設定に従います。
`--samples` を増やす場合は本体の測定間隔（多くは5秒）を考慮して制限時間も増やしてください。
SCD40は初回に約5.5秒待ちます。測定終了後も本体と同じく周期測定を維持します。
ENS160の準備中や無効状態は合格にしません。準備中の場合は時間を置くか制限時間を延長します。
ENS160単独診断はBME280の値を取得しないため、新しい温湿度補正を書き込みません。

PIRは静止中の `0` も通信成功です。検知能力は前で動き、`0` と `1` が切り替わることを確認してください。
BH1750は明暗を変えて値の変化を確認してください。温湿度・気圧・CO₂等の精度は基準計器との比較が別途必要です。
カメラ診断は画像を保存せず、顔認識やタッチパネルの操作は検証しません。
カメラ指定はローカルの番号または `/dev/videoN` に限定し、ネットワークURLや動画ファイルは受け付けません。
SwitchBot温湿度計はクラウドAPI経由のため、このローカル物理センサー診断には含めません。
旧 `bh1750_loop.py` と `sr501_diag.py` は従来の補助診断として残しています。

## ハードウェア不要の自動テスト

```bash
cd ~/deskclock
./venv/bin/python -m pip install -r requirements-dev.txt
./venv/bin/python -m pytest -q
```

`pytest.ini` により `tests/` だけを収集し、実機診断が誤って実行されることを防ぎます。
既存のpytest形式・unittest形式の両方を実行します。サービス稼働中でも実行できます。
追加分だけなら標準ライブラリのunittestで実行できます。

```bash
./venv/bin/python -m unittest discover -s tests -p test_physical_sensors.py -v
```

追加テストでは全8種類を対象に、正常値・通信失敗・再試行・CRC・バイト順・補正・
古い値の保持・GPIO検知・カメラ解放・診断の鮮度判定を検証します。
既存AHT21テストのbusy/初期化検証、BME280の既知値計算テスト等も継続して実行します。
モックによる成功は実機の接続や測定精度の保証ではありません。

## 診断結果のプライバシー

この診断プログラムはクラウドAPI呼び出しや結果の自動送信を行いません。
カメラ画像はメモリ内で読み取り、出力は画像の幅・高さだけです。
標準出力と任意のJSONファイルには室内の測定値や人感の状態が含まれ、
エラーにはローカルのパスや機器名が含まれる可能性があります。
これらは在室状況・利用環境の手掛かりになるため、GitHub等へ結果を共有する場合は内容を確認してください。
リリース用ZIPには測定結果、画像、ログ、環境変数ファイルを収録しません。
