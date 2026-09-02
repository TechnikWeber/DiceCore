[English](NETWORK.md) · **Deutsch**

# Die Kiste ins Netzwerk bringen

Ein Würfelturm steht im Regal, ohne Tastatur und ohne Bildschirm. Wenn er das WLAN nicht
erreicht — neue Wohnung, geändertes Passwort, fremder Tisch —, muss es einen Weg hinein
geben, der keine SSH-Sitzung ist, denn es gibt keine Sitzung.

Die Antwort ist dieselbe wie bei YonderRC: **die Kiste macht ein eigenes Netz auf.** Ein
Handy verbindet sich damit, ein Captive Portal öffnet die Einrichtungsseite, ohne dass
jemand eine Adresse tippt, und von dort sagt man ihr, in welches Netz sie soll.

## Was sie von allein tut

```
45 Sekunden ohne Netz  →  öffnet „DiceCore-setup"  →  Handy verbindet  →  Seite geht auf
```

- **45 Sekunden, nicht sofort.** Ein neu startender Router nimmt das Netz für zwanzig
  Sekunden weg, und eine Kiste, die dabei jedes Mal mit ihrem eigenen Funk davonläuft, ist
  schlimmer als eine, die wartet. Die Wartezeit ist einstellbar.
- **Das Netz ist standardmäßig offen.** Wem man die Kiste nicht erreichen kann, dem kann man
  auch kein Passwort mitteilen. Setz eines, wenn das Regal öffentlich steht.
- **Das Portal braucht Port 80**, also root. Ohne das erscheint das Netz trotzdem und die
  Einrichtungsseite funktioniert — sie muss nur eingetippt werden
  (`http://10.42.0.1:8099/setup`).
- **DNS wird nur umgebogen, wenn die Kiste selbst keine Verbindung nach draußen hat.** Mit
  einer teilt der Hotspot echtes Internet, und alle Namen auf die Kiste zu zeigen würde das
  für jeden Verbundenen kaputt machen und dabei ein Portal auslösen, das niemand braucht.

## Einem Netzwerk beitreten

**Setup → Network.** Scannen, auswählen, Passwort tippen, verbinden.

Eines ist zu erwarten: **die Kiste hat einen Funk**, also schließt das Beitreten das Netz,
das sie selbst anbietet — einschließlich der Verbindung, über die du gerade die Seite liest,
falls du darüber gekommen bist. Das ist kein Fehler. Geh zurück in dein eigenes WLAN, dann
ist die Kiste auch dort. Die Seite sagt das vorher, statt scheinbar hängen zu bleiben.

Ist das Passwort falsch, **macht die Kiste ihr eigenes Netz wieder auf**, statt unerreichbar
dazusitzen. Genau dafür wird der Hotspot nach einem Fehlschlag zurückgeholt.

## Das WLAN-Land, und warum ohne es nichts geht

**Ein Raspberry Pi sendet nicht, bevor er weiß, wessen Funkregeln gelten.** Bis dahin ist der
Funk software-gesperrt, und NetworkManager meldet:

```
Error: Device is not available.
```

— ein Satz, dessen Bedeutung niemand errät. Es ist der mit Abstand häufigste Grund, warum der
Hotspot eines frischen Pi nie auftaucht. Einmal auf der Netzwerkseite setzen, oder:

```bash
sudo raspi-config nonint do_wifi_country DE
```

Die Seite liest den Funkzustand aus und sagt, welches der möglichen Probleme es tatsächlich
ist — ein Hardware-Schalter, ein fehlendes Land, oder schlicht nichts in Reichweite.

## Ethernet

Nichts einzurichten: ein Kabel ist ein Kabel, NetworkManager bringt es hoch, und die Kiste
ist unter der Adresse erreichbar, die sie bekommt. Die Netzwerkseite zeigt sie, und eine
Ethernet-Verbindung zählt als Verbindung nach draußen — eine Kiste am Kabel macht also nie
ihr eigenes Netz auf, und wenn man sie darum bittet, teilt sie die Kabelverbindung, statt
DNS umzubiegen.

## Als root laufen

Der Dienst läuft als root, und das ist ein bewusster Handel, kein Versehen. Zwei Dinge
brauchen es, und beide sind der Unterschied zwischen einer Kiste, die man zurückholen kann,
und einer, die man nicht zurückholen kann:

- WLAN über NetworkManager steuern, **wenn das Netz schon weg ist**, und
- Port 80 für das Captive Portal belegen.

Auf der Einrichtungsseite gibt es keinen Zugangsschutz. In einem Heimnetz ist das ein
vertretbarer Ort dafür; in einem geteilten sollte man es wissen, bevor man einsteckt.

## Was sie nicht kann

- **Zwischen zwei bekannten Netzen wählen.** Sie geht in das, was man ihr sagt, und bleibt.
- **Versteckte Netze** stehen in keinem Scan; den Namen von Hand eintippen.
- **Enterprise-WLAN** (WPA2-Enterprise, eduroam und Verwandte) wird gar nicht behandelt.
- **Ein zweiter Funk.** Mit einem schließen Anbieten und Beitreten einander aus, und um diese
  Einschränkung herum ist der ganze Entwurf gebaut.
