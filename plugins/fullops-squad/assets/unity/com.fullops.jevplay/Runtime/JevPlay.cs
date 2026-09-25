// FullOps Jev play bridge for jev_test_unity.py. Only with --jev-play <dir>: freezes the game at each decision, writes
// state-<n>.json, waits for action-<n>.json and plays it through queued Input System keys. Normal launches do nothing.
// Game-specific parts (actors, fields, keys) come from <dir>/config.json, so the game repo needs no bridge code.
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.RegularExpressions;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.LowLevel;

namespace Fullops.JevPlay
{
    [Serializable] public class Group { public string name; public string[] patterns; }
    [Serializable] public class FieldPath { public string name; public string path; }
    [Serializable] public class KeyAction { public string name; public string key; public string note; }
    [Serializable] public class MoveKeys { public string up = "W", down = "S", left = "A", right = "D"; }

    [Serializable]
    public class Config
    {
        public string player;
        public Group[] groups = new Group[0];
        public FieldPath[] fields = new FieldPath[0];
        public KeyAction[] keys = new KeyAction[0];
        public MoveKeys move = new MoveKeys();
        public float reach = 1.2f, approachSeconds = 3f, pressSeconds = 0.15f, waitSeconds = 1f, startDelay = 1f;
        public float decisionTimeout = 120f;
        public int maxDecisions = 200;
    }

    [Serializable] public class Actor { public string name, group, direction; public float x, y, distance; public bool withinReach; }
    [Serializable] public class Field { public string name, value, error; }
    [Serializable] public class Choice { public string id, description; }

    [Serializable]
    public class State
    {
        public int step;
        public float gameTime;
        public bool gamePaused;  // 게임이 스스로 멈춘 상태(레벨업 선택 등). 이때 이동은 진행되지 않고 입력만 받는다
        public Actor player;
        public Actor[] actors;
        public Field[] fields;
        public string[] texts;
        public Choice[] actions;
        public string lastAction, lastOutcome;
    }

    [Serializable] public class ActionFile { public int step; public string action; }
    [Serializable] public class Result { public string reason; public int decisions; }

    public sealed class JevPlay : MonoBehaviour
    {
        string dir;
        Config config;
        Transform playerTransform;
        string lastAction = "", lastOutcome = "";
        float gameScale = 1f;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Launch()
        {
            var args = Environment.GetCommandLineArgs();
            int i = Array.IndexOf(args, "--jev-play");
            if (i < 0) return;
            if (i + 1 >= args.Length) { Application.Quit(2); return; }
            string path = Path.GetFullPath(args[i + 1]), file = Path.Combine(path, "config.json");
            if (!File.Exists(file)) { Application.Quit(2); return; }
            var runner = new GameObject("FullOps Jev play").AddComponent<JevPlay>();
            DontDestroyOnLoad(runner.gameObject);
            runner.dir = path;
            runner.config = JsonUtility.FromJson<Config>(File.ReadAllText(file));
            Application.runInBackground = true;
            InputSystem.settings.backgroundBehavior = InputSettings.BackgroundBehavior.IgnoreFocus;
            if (Keyboard.current == null) InputSystem.AddDevice<Keyboard>();
        }

        IEnumerator Start()
        {
            yield return new WaitForSecondsRealtime(config.startDelay);
            for (int step = 1; step <= config.maxDecisions; step++)
            {
                // 결정하는 동안 게임을 멈춰 Jev 지연이 게임에 영향을 주지 않게 한다. 게임이 스스로 멈춘 상태는 기억했다가 그대로 돌려준다
                gameScale = Time.timeScale;
                Time.timeScale = 0f;
                var choices = Choices();
                Write($"state-{step}.json", JsonUtility.ToJson(Snapshot(step, choices)));
                string actionPath = Path.Combine(dir, $"action-{step}.json");
                float waited = 0f;
                ActionFile action = null;
                while (action == null)
                {
                    if (waited > config.decisionTimeout) { Finish("decision timeout", step - 1); yield break; }
                    if (File.Exists(actionPath))
                        try { action = JsonUtility.FromJson<ActionFile>(File.ReadAllText(actionPath)); }
                        catch (IOException) { }  // Windows에서 파일을 교체하는 중이면 다음 틱에 다시 읽는다
                    if (action == null) { yield return new WaitForSecondsRealtime(0.05f); waited += 0.05f; }
                }
                Time.timeScale = gameScale;
                if (action.action == "quit") { Finish("quit", step); yield break; }
                if (!choices.Any(c => c.id == action.action)) { lastAction = action.action; lastOutcome = "unknown action"; continue; }
                lastAction = action.action;
                yield return Play(action.action);
            }
            Finish("max decisions", config.maxDecisions);
        }

        IEnumerator Play(string id)
        {
            var parts = id.Split(':');
            if (parts[0] == "approach")
            {
                float until = Time.unscaledTime + config.approachSeconds;  // 게임이 멈춰도 끝나도록 실제 시간으로 잰다
                Actor target = null;
                while (Time.unscaledTime < until)
                {
                    target = Nearest(parts[1]);
                    if (target == null) { lastOutcome = "target gone"; break; }
                    if (target.withinReach) break;
                    Hold(target.x - Player().x, target.y - Player().y);
                    yield return null;
                }
                Hold(0, 0);
                yield return null;
                target = Nearest(parts[1]);
                lastOutcome = target == null ? "target gone" : target.withinReach ? "reached" :
                    $"still {target.distance:0.0} away" + (Time.timeScale == 0f ? " (game paused)" : "");
            }
            else if (parts[0] == "press")
            {
                var key = config.keys.First(k => k.name == parts[1]);
                if (!Enum.TryParse(key.key, true, out Key code)) { lastOutcome = $"unknown key {key.key}"; yield break; }
                InputSystem.QueueStateEvent(Keyboard.current, new KeyboardState(code));
                yield return null;
                yield return new WaitForSecondsRealtime(config.pressSeconds);
                InputSystem.QueueStateEvent(Keyboard.current, new KeyboardState());
                yield return null;
                lastOutcome = "pressed";
            }
            else
            {
                yield return new WaitForSecondsRealtime(config.waitSeconds);
                lastOutcome = "waited";
            }
        }

        void Hold(float dx, float dy)
        {
            var keys = new List<Key>();
            const float dead = 0.15f;
            if (dx > dead) Add(keys, config.move.right); else if (dx < -dead) Add(keys, config.move.left);
            if (dy > dead) Add(keys, config.move.up); else if (dy < -dead) Add(keys, config.move.down);
            InputSystem.QueueStateEvent(Keyboard.current, new KeyboardState(keys.ToArray()));
        }

        static void Add(List<Key> keys, string name)
        {
            if (Enum.TryParse(name, true, out Key code)) keys.Add(code);
        }

        List<Choice> Choices()
        {
            var result = new List<Choice>();
            foreach (var g in config.groups)
            {
                var near = Nearest(g.name);
                if (near != null)
                    result.Add(new Choice { id = "approach:" + g.name,
                        description = $"Move toward the nearest {g.name} ({near.name}, {near.distance:0.0} units {near.direction})." });
            }
            foreach (var k in config.keys)
                result.Add(new Choice { id = "press:" + k.name, description = string.IsNullOrEmpty(k.note) ? $"Press {k.key} ({k.name})." : k.note });
            result.Add(new Choice { id = "wait", description = $"Let the game run for {config.waitSeconds:0.#} seconds without input." });
            return result;
        }

        State Snapshot(int step, List<Choice> choices) => new State
        {
            step = step, gameTime = Time.time, gamePaused = gameScale == 0f, player = Player(), actors = Actors(), fields = Fields(), texts = Texts(),
            actions = choices.ToArray(), lastAction = lastAction, lastOutcome = lastOutcome,
        };

        Actor Player()
        {
            if (playerTransform == null || !playerTransform.gameObject.activeInHierarchy)
                playerTransform = Find(new[] { config.player }).FirstOrDefault();
            var p = playerTransform;
            return p == null ? null : new Actor { name = p.name, group = "player", x = p.position.x, y = p.position.y };
        }

        Actor[] Actors()
        {
            var player = Player();
            var result = new List<Actor>();
            foreach (var g in config.groups)
                foreach (var t in Find(g.patterns))
                {
                    float dx = t.position.x - (player?.x ?? 0), dy = t.position.y - (player?.y ?? 0), d = Mathf.Sqrt(dx * dx + dy * dy);
                    result.Add(new Actor { name = t.name, group = g.name, x = t.position.x, y = t.position.y, distance = d,
                        direction = Direction(dx, dy), withinReach = player != null && d <= config.reach });
                }
            return result.OrderBy(a => a.distance).Take(24).ToArray();
        }

        Actor Nearest(string group) => Actors().FirstOrDefault(a => a.group == group);

        static IEnumerable<Transform> Find(IEnumerable<string> patterns)
        {
            var regexes = patterns.Where(p => !string.IsNullOrEmpty(p))
                .Select(p => new Regex("^" + Regex.Escape(p).Replace("\\*", ".*") + "$")).ToArray();
            return FindObjectsByType<Transform>(FindObjectsSortMode.None)
                .Where(t => t.gameObject.activeInHierarchy && regexes.Any(r => r.IsMatch(t.name)));
        }

        static string Direction(float dx, float dy)
        {
            if (Mathf.Abs(dx) < 0.15f && Mathf.Abs(dy) < 0.15f) return "here";
            string[] names = { "east", "north-east", "north", "north-west", "west", "south-west", "south", "south-east" };
            int index = Mathf.RoundToInt(Mathf.Atan2(dy, dx) / (Mathf.PI / 4f));
            return names[(index + 8) % 8];
        }

        Field[] Fields() => config.fields.Select(f =>
        {
            try { return new Field { name = f.name, value = Read(f.path) }; }
            catch (Exception e) { return new Field { name = f.name, error = e.Message }; }
        }).ToArray();

        // "Type.member.member": 첫 인스턴스(또는 static)의 필드·속성을 따라간다. 이름이 바뀌면 오류를 그대로 보고한다
        static string Read(string path)
        {
            var parts = path.Split('.');
            var type = AppDomain.CurrentDomain.GetAssemblies().Select(a => a.GetTypes().FirstOrDefault(t => t.Name == parts[0]))
                .FirstOrDefault(t => t != null) ?? throw new Exception($"type {parts[0]} not found");
            object value = typeof(UnityEngine.Object).IsAssignableFrom(type) ? FindFirstObjectByType(type) : null;
            const BindingFlags any = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static;
            foreach (var name in parts.Skip(1))
            {
                var field = type.GetField(name, any);
                var property = field == null ? type.GetProperty(name, any) : null;
                if (field == null && property == null) throw new Exception($"{type.Name}.{name} not found");
                value = field != null ? field.GetValue(field.IsStatic ? null : value) : property.GetValue(property.GetMethod.IsStatic ? null : value);
                if (value == null) return "null";
                type = value.GetType();
            }
            return value is float f ? f.ToString("0.##") : value.ToString();
        }

        static string[] Texts()
        {
            var result = new List<string>();
            foreach (var name in new[] { "UnityEngine.UI.Text, UnityEngine.UI", "TMPro.TMP_Text, Unity.TextMeshPro" })
            {
                var type = Type.GetType(name);
                if (type == null) continue;
                foreach (var component in FindObjectsByType(type, FindObjectsSortMode.None).OfType<Behaviour>())
                    if (component.isActiveAndEnabled && type.GetProperty("text")?.GetValue(component) is string text && text.Trim().Length > 0)
                        result.Add(text.Trim().Length > 160 ? text.Trim().Substring(0, 160) : text.Trim());
            }
            return result.Distinct().Take(30).ToArray();
        }

        void Write(string name, string json)
        {
            string path = Path.Combine(dir, name), temporary = path + ".tmp";
            File.WriteAllText(temporary, json);
            if (File.Exists(path)) File.Delete(path);
            File.Move(temporary, path);
        }

        void Finish(string reason, int decisions)
        {
            Time.timeScale = gameScale;
            InputSystem.QueueStateEvent(Keyboard.current, new KeyboardState());
            Write("result.json", JsonUtility.ToJson(new Result { reason = reason, decisions = decisions }));
            Application.Quit(0);
        }
    }
}
