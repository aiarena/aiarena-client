function generateDynamicTable() {
  $(function() {
    $.ajax({
      url: "/get_results",
      type: "GET",

      dataType: "json"
    }).done(function(data) {
      var myResults = data;

      var noOfResults = myResults.length;

      if (noOfResults > 0) {
        // CREATE DYNAMIC TABLE.
        var table = document.createElement("table");

        table.setAttribute("style", "overflow-x:auto;");

        // retrieve column header

        var col = []; // define an empty array
        for (var i = 0; i < noOfResults; i++) {
          for (var key in myResults[i]) {
            if (col.indexOf(key) === -1) {
              col.push(key);
            }
          }
        }

        // CREATE TABLE HEAD .
        var tHead = document.createElement("thead");

        // CREATE ROW FOR TABLE HEAD .
        var hRow = document.createElement("tr");

        // ADD COLUMN HEADER TO ROW OF TABLE HEAD.
        for (var i = 0; i < col.length; i++) {
          var th = document.createElement("th");
          th.innerHTML = col[i];
          hRow.appendChild(th);
        }
        tHead.appendChild(hRow);
        table.appendChild(tHead);

        // CREATE TABLE BODY .
        var tBody = document.createElement("tbody");

        // ADD COLUMN HEADER TO ROW OF TABLE HEAD.
        for (var i = noOfResults - 1; i >= 0; i--) {
          var bRow = document.createElement("tr"); // CREATE ROW FOR EACH RECORD .

          for (var j = 0; j < col.length; j++) {
            var td = document.createElement("td");
            var value = myResults[i][col[j]];
            if (col[j] == "ReplayPath") {
              var filename = value.replace(/^.*[\\\/]/, "");
              value = '<a href="/replays/' + filename + '" download>Replay</a>';
            }

            td.innerHTML = value;

            bRow.appendChild(td);
          }
          tBody.appendChild(bRow);
        }
        table.appendChild(tBody);

        // FINALLY ADD THE NEWLY CREATED TABLE WITH JSON DATA TO A CONTAINER.
        var divContainer = document.getElementById("myResults");
        divContainer.innerHTML = "";
        divContainer.appendChild(table);
      } else {
        var divContainer = document.getElementById("myResults");
        divContainer.innerHTML = "<p>No Results</p>";
      }
      setTimeout(generateDynamicTable, 30000);
    });
  });
}


try {
  window.sock = new WebSocket("ws://" + window.location.host + "/game_running");
} catch (err) {
  window.sock = new WebSocket("wss://" + window.location.host + "/game_running");
}

// show message in div#subscribe
function showMessage(message) {
  var messageElem = $("#subscribe"),
    height = 0,
    date = new Date();
  options = { hour12: false };

  messageElem.html(
    $("<label>").html(
      "[" + date.toLocaleTimeString("en-US", options) + "] " + message + "\n"
    )
  );
  messageElem.find("p").each(function(i, value) {
    height += parseInt($(this).height());
  });

  messageElem.animate({ scrollTop: height });
}


window.sock.onopen = function() {
  showMessage("Connection to server started");
};

// send message from form
$("#submit").click(function() {
  sendMessage();
});

$("#message").keyup(function(e) {
  if (e.keyCode == 13) {
    sendMessage();
  }
});

// income message handler
window.sock.onmessage = function(event) {
  showMessage(event.data);
};

$("#signout").click(function() {
  window.location.href = "signout";
});

window.sock.onclose = function(event) {
  if (event.wasClean) {
    showMessage("Clean connection end");
  } else {
    showMessage("Connection broken");
  }
};

window.sock.onerror = function(error) {
  showMessage(error);
};
