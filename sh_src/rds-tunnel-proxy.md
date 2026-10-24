# rds-tunnel-proxy

dev と stg の DB（RDS）にローカルからつなぐための、SSH の `ProxyCommand` 用のスクリプト。踏み台の EC2 へ SSM 経由で SSH をつなぐ。

踏み台が作り直されていたら、つなぐ前にリカバリー（`rds-tunnel-recovery`、`rds-tunnel-recovery-stg` と同じ処理）を自動でする。ターミナルの `ssh -N rds-tunnel`（stg は `rds-tunnel-stg`）からも、DataGrip の SSH トンネルからも使える。

- [設定](#設定)
- [トンネルの仕組み](#トンネルの仕組み)
- [踏み台が作り直されると、なぜつながらなくなるか](#踏み台が作り直されるとなぜつながらなくなるか)
- [リカバリーの仕組み](#リカバリーの仕組み)
- [cmd-craft/sh_src/rds-tunnel-proxy の説明](#cmd-craftsh_srcrds-tunnel-proxy-の説明)
- [困ったとき](#困ったとき)

## 設定

### ~/.ssh/config

```
Host rds-tunnel
    User ssm-user
    IdentityFile ~/.ssh/<踏み台用の秘密鍵>
    ProxyCommand /Users/nishimuratakuya/bin/cmd-craft/sh_src/rds-tunnel-proxy %p

Host rds-tunnel-stg
    User ssm-user
    IdentityFile ~/.ssh/<踏み台用の秘密鍵>
    ProxyCommand /Users/nishimuratakuya/bin/cmd-craft/sh_src/rds-tunnel-proxy %p stg
```

`LocalForward` は書かない。DataGrip は `~/.ssh/config` の `LocalForward` も読み、そのポート（5433 番など）でも待ち受けてしまうため。ターミナルでトンネルが要るときは、`ssh` に `-L` を付ける（「③ ポート転送」を参照）。

スクリプトの引数は次の 2 つ。

| 引数 | 意味 |
|---|---|
| 1 つ目 | 踏み台でつなぐポート。`%p` と書くと、ssh が 22 に置き換える |
| 2 つ目 | 環境。`dev` か `stg`。省くと `dev` |

### DataGrip

データソースの設定で、次のように入れる。

| タブ | 項目 | dev | stg |
|---|---|---|---|
| SSH/SSL | Use SSH tunnel | オン | オン |
| SSH/SSL | Host / Port | `rds-tunnel` / `22` | `rds-tunnel-stg` / `22` |
| SSH/SSL | Username | `ssm-user` | `ssm-user` |
| SSH/SSL | Authentication type | OpenSSH config and authentication agent | OpenSSH config and authentication agent |
| SSH/SSL | Local port | 空欄 | 空欄 |
| General | Host / Port | dev の RDS のエンドポイント / `5432` | stg の RDS のエンドポイント / `5432` |

DataGrip は自分でポート転送をする。そのため General の Host と Port には、`localhost:5433` ではなく、踏み台から見た RDS の宛先を書く。

Local port は空欄にする。空欄なら、手元で開けるポートを DataGrip が空いている番号から選ぶので、ほかの接続やターミナルの `ssh -N` とぶつからない。

- 番号を入れると、その番号で待ち受ける。接続を複製すると、複製元の番号も引き継がれるので注意する
- 空欄にしても、開き直すと薄い文字で番号が出ることがある。これは入力欄の見本で、設定には入っていない

### 使う環境変数（`cmd-craft/.env`）

| 変数 | 使い道 |
|---|---|
| `DEV_BASTION` | dev の踏み台の EC2 の Name タグ。インスタンス ID を引くのに使う |
| `STG_BASTION` | stg の踏み台の EC2 の Name タグ |
| `PUBLIC_KEY_FILE_FOR_BASTION` | 踏み台に登録する公開鍵のファイル名（`~/.ssh/` の下） |
| `REMOTE_USER` | 踏み台のユーザー（`ssm-user`） |

## トンネルの仕組み

RDS と踏み台は VPC の中にあり、ローカルから直接はつながらない。踏み台にも、外から入るためのポートは開いていない。そこで、3 つの層を重ねてつなぐ。下の層の上を、上の層の通信が流れる。

dev をターミナルから `-L 5433:<dev の RDS のエンドポイント>:5432` でつなぐときの例:

```
③ ポート転送   localhost:5433 ──────────────────────────────> RDS:5432
② SSH         ssh ────────────────────────────────────────> 踏み台の sshd:22
① SSM         aws ssm start-session ──> AWS SSM ──> 踏み台の SSM エージェント
```

### ① SSM のセッション

`aws ssm start-session` が、AWS の Systems Manager（SSM）を中継して、踏み台の中の SSM エージェントとの通信路を作る。`AWS-StartSSHSession` を指定すると、エージェントはこの通信路を踏み台の `localhost:22`（sshd）につなぐ。

- 踏み台のほうから SSM につなぎに行く仕組みなので、踏み台に入るためのポートを開けなくてよい
- 認証は IAM。`~/.aws/credentials` の一時的な認証情報を使う

### ② SSH

`ProxyCommand` に書いたコマンドは、ssh が TCP で直接つなぐ代わりに使う通信路になる。ssh はこのコマンドの標準入力に書き、標準出力から読む。つまり、① の通信路の上で SSH をやりとりする。

- ユーザーの認証: `ssm-user` と鍵（`IdentityFile`）
- サーバーの確認: `~/.ssh/known_hosts` に残したホスト鍵と比べる

### ③ ポート転送

SSH のローカルフォワード（コマンドでは `-L`、設定ファイルでは `LocalForward`）を使う。手元のポートに来た通信を、SSH の通信路の中を通して踏み台まで運び、踏み台から先の宛先（RDS）に届ける。

```
DataGrip / psql ──> localhost:5433 ══ SSH の通信路 ══> 踏み台 ──> RDS:5432
```

RDS には VPC の中からしかつながらないが、踏み台は VPC の中にあるのでつながる。そこで、踏み台に代わりにつないでもらう。

- DataGrip: SSH トンネルの設定から、DataGrip が自分で空いているポートを選んで転送する
- ターミナル: `-L <手元のポート>:<宛先>:<宛先のポート>` を付ける。動かしている間、手元のポート（例では 5433 番）が RDS につながる。`-N` は、リモートでコマンドを実行せず転送だけをする指定

  ```
  ssh -N -L 5433:<dev の RDS のエンドポイント>:5432 rds-tunnel
  ssh -N -L 5434:<stg の RDS のエンドポイント>:5432 rds-tunnel-stg
  ```

## 踏み台が作り直されると、なぜつながらなくなるか

踏み台の EC2 は sq-infrastructure の `stack/bastion/v2` で管理している。AWS が新しい AMI を出すと、次の terraform apply でインスタンスが作り直され、次の 3 つが変わる。

| 変わるもの | 起きること | 対処 |
|---|---|---|
| インスタンス ID | 古い ID には SSM でつながらない（①） | 接続のたびに Name タグから ID を引く |
| SSH のホスト鍵 | `known_hosts` と合わず、ssh が `REMOTE HOST IDENTIFICATION HAS CHANGED!` で止まる（②） | `known_hosts` から古い行を消す |
| `authorized_keys` | 起動時の cloud-config で空のファイルが作られ、公開鍵が消える。`Permission denied (publickey)` になる（②） | 公開鍵を登録し直す |

インスタンス ID は以前から接続のたびに引いていた。手で `rds-tunnel-recovery` を実行していたのは、残りの 2 つのため。

## リカバリーの仕組み

### 作り直しの見分け方

前回つないだ踏み台のインスタンス ID を、Host 名ごとのファイルに残しておく。今回引いた ID と違えば、作り直されたとみなしてリカバリーをする。

| 環境 | ファイル |
|---|---|
| dev | `~/.cache/cmd-craft/rds-tunnel-instance-id` |
| stg | `~/.cache/cmd-craft/rds-tunnel-stg-instance-id` |

同じ ID なら何もしないので、ふだんの接続は遅くならない。

### ホスト鍵

`known_hosts` から、その環境の Host 名（`rds-tunnel` か `rds-tunnel-stg`）の行を消す。次の接続で、新しいホスト鍵を受け入れるか聞かれる。ターミナルでは `yes` と入力し、DataGrip ではダイアログで受け入れる。

### 公開鍵

まだ SSH ではログインできないので、SSM の Run Command（`aws ssm send-command`）を使い、踏み台でシェルのコマンドを実行させる。Run Command は IAM で認証するので、SSH の鍵がなくても使える。

コマンドは踏み台の root として動き、`authorized_keys` に公開鍵を追記する。鍵がすでにあれば追記しない。

### 手でリカバリーしたいとき

その環境のキャッシュを消すと、次の接続でリカバリーが動く。

```
rm ~/.cache/cmd-craft/rds-tunnel-instance-id      # dev
rm ~/.cache/cmd-craft/rds-tunnel-stg-instance-id  # stg
```

これまでの `rds-tunnel-recovery`、`rds-tunnel-recovery-stg` も、そのまま使える。

## cmd-craft/sh_src/rds-tunnel-proxy の説明

スクリプトの上から順に説明する。

### 準備

| コマンド | 意味 |
|---|---|
| `set -euo pipefail` | `-e`: コマンドが失敗したらそこで止まる。`-u`: 定義していない変数を使ったらエラーにする。`pipefail`: パイプの途中のコマンドの失敗も失敗とみなす |
| `export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"` | `~/.zprofile` の PATH は、ターミナルの zsh でしか読まれない。DataGrip のような GUI のアプリから呼ばれると、PATH が `/usr/bin:/bin` などだけになり、Homebrew の `aws` や `jq` が見つからないことがある。そのため足しておく。同じ理由で、`~/.ssh/config` の `ProxyCommand` もフルパスで書く |
| `load_env_vars` | `cmd-craft/.env` の変数を読み込む |
| `[[ "$port" =~ ^[0-9]+$ ]] \|\| port=22` | 1 つ目の引数が数字でなければ（`%p` がそのまま渡ってきたときなど）、22 を使う |
| `case "$env" in ...` | 2 つ目の引数（`dev` か `stg`）から、`~/.ssh/config` の Host 名（`rds-tunnel` か `rds-tunnel-stg`）を決める。ほかの値ならエラーで止まる |

### 踏み台のインスタンス ID を引く

同じディレクトリの `get-dev-bastion-instance-id`（stg は `get-stg-bastion-instance-id`）をパスで呼ぶ（PATH には頼らない）。中では次を実行している。

```
aws ec2 describe-instances \
    --filters "Name=tag:Name,Values=${DEV_BASTION}" "Name=instance-state-name,Values=running" \
    --query "Reservations[].Instances[?State.Name=='running'][].InstanceId" \
    --output json | jq -r '.[]'
```

Name タグが `DEV_BASTION`（stg は `STG_BASTION`）で、動いているインスタンスの ID を出す。念のため `head -n 1` で 1 つ目だけを使う。

### ホスト鍵を消す

```
ssh-keygen -R "$host_alias" >/dev/null 2>&1 || true
```

- `-R <ホスト名>`: `known_hosts` から、そのホストの行を消す。`$host_alias` は `rds-tunnel` か `rds-tunnel-stg`。消す前のファイルは `known_hosts.old` に残る
- `>/dev/null 2>&1`: 結果を標準出力に出すので捨てる（理由は「[標準出力に何も出さない](#標準出力に何も出さない)」）
- `|| true`: 消す行がないなどで失敗しても、止まらないようにする

### 公開鍵を登録する

```
aws ssm send-command \
    --instance-ids "$instance_id" \
    --document-name "AWS-RunShellScript" \
    --parameters "$(jq -n --arg c "<踏み台で実行するコマンド>" '{commands: [$c]}')" \
    --comment "Register public key for SSH access" \
    --query "Command.CommandId" \
    --output text
```

| オプション | 意味 |
|---|---|
| `--document-name "AWS-RunShellScript"` | 踏み台でシェルのコマンドを実行する、AWS が用意しているドキュメント |
| `--parameters` | 実行するコマンドを `{"commands": ["..."]}` という JSON で渡す。公開鍵にはスペースや記号が入るので、`jq` で JSON を組み立てて、引用符の扱いを間違えないようにしている |
| `--query "Command.CommandId" --output text` | 結果から、コマンドの ID だけを取り出す。次の「待つ」で使う |

踏み台で実行するコマンドは次のとおり。

```
grep -qxF '<公開鍵>' /home/ssm-user/.ssh/authorized_keys || echo '<公開鍵>' >> /home/ssm-user/.ssh/authorized_keys
```

- `grep -qxF`: `-F` は文字列をそのまま探す（正規表現として扱わない）。`-x` は行全体が一致するものだけを探す。`-q` は何も出さず、見つかったかどうかだけを返す
- `A || B`: A が失敗したとき（鍵が見つからなかったとき）だけ B を実行する。何度実行しても、鍵は重複しない
- `>>`: ファイルの末尾に追記する

### 登録が終わるのを待つ

```
aws ssm wait command-executed --command-id "$command_id" --instance-id "$instance_id"
```

`send-command` は、コマンドを送っただけで戻ってくる。登録が終わる前に SSH を始めると、鍵がなくて失敗する。そのため、実行が終わるまで待つ（5 秒ごとに確かめる）。踏み台でコマンドが失敗したら、ここでエラーになって止まる。

### SSM のセッションを開く

```
exec aws ssm start-session \
    --target "$instance_id" \
    --document-name AWS-StartSSHSession \
    --parameters "portNumber=${port}"
```

- `AWS-StartSSHSession`: 踏み台の指定したポート（22）につなぐ、SSH 用のドキュメント。ローカルの中継には `session-manager-plugin` を使う
- `exec`: このスクリプトのプロセスを `aws ssm start-session` に置き換える。ssh とつながった標準入出力を、そのまま引き継ぐ

### 標準出力に何も出さない

ProxyCommand の標準出力は、そのまま SSH の通信路になる。スクリプトが `echo` などで文字を出すと、ssh はそれを SSH のデータとして読んでしまい、接続が壊れる。

そのため、このスクリプトでは次のようにしている。

- メッセージは `>&2` で標準エラーに出す
- 標準出力に結果を出すコマンドは、`$( )` で変数に受けるか、`>/dev/null` で捨てる

## 困ったとき

| 症状 | 原因と対処 |
|---|---|
| `ExpiredToken` などの AWS のエラー | 一時的な認証情報が切れている。`setup-aws-credentials-v2` で作り直す |
| `Error: Cannot find running dev bastion instance`（stg も同様） | 踏み台が止まっているか、作り直しの途中。少し待ってからつなぎ直す |
| `Error: Unknown environment` | `ProxyCommand` の 2 つ目の引数が `dev`・`stg` 以外になっている |
| `Permission denied (publickey)` | 鍵の登録とキャッシュがずれている。その環境のキャッシュを消してつなぎ直す |
| `bind [127.0.0.1]:5433: Address already in use` | 手元の 5433 番を、ほかのプロセス（DataGrip など）が使っている。`lsof -nP -iTCP:5433 -sTCP:LISTEN` で確かめ、`-L` で別の番号を使う |
| DataGrip だけ鍵の認証に失敗する | DataGrip は ssh-agent の鍵を使う。`ssh-add --apple-use-keychain ~/.ssh/<秘密鍵>` で鍵を入れる |
| どこで止まっているか知りたい | `ssh -v rds-tunnel true`（stg は `rds-tunnel-stg`）で、スクリプトのメッセージと ssh の詳しいログを見る |
