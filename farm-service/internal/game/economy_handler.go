package game

import (
	"bdc/farm-service/internal/farm"
	"bdc/farm-service/internal/game/dto"
	domain "bdc/farm-service/internal/gamedomain"
	"fmt"
	"github.com/jackc/pgx/v5"
	"net/http"
	"time"
)

func (s *Server) registerEconomy() {
	s.route("GET", "/api/game/state", []string{"PLAYER"}, func(w http.ResponseWriter, r *http.Request, u User) error {
		var state map[string]any
		e := s.withGame(r, u, func(tx pgx.Tx, g *gameTx) error {
			historyRows, e := tx.Query(r.Context(), `SELECT event_type,kind,quantity,coins_delta,created_at FROM economy_ledger WHERE farm_id=$1 ORDER BY created_at DESC LIMIT 8`, g.Farm.ID)
			if e != nil {
				return e
			}
			history := []map[string]any{}
			for historyRows.Next() {
				var typ, kind string
				var qty, coins int
				var at time.Time
				if e = historyRows.Scan(&typ, &kind, &qty, &coins, &at); e != nil {
					break
				}
				history = append(history, map[string]any{"type": typ, "kind": kind, "quantity": qty, "coins": coins, "at": at})
			}
			if e == nil {
				e = historyRows.Err()
			}
			historyRows.Close()
			if e != nil {
				return e
			}
			state = map[string]any{"farm": g.Farm, "life": map[string]any{"hungerPct": g.Life.Hunger * 100 / domain.FarmerHungerCap, "insects": g.Life.Insects, "nextInsectIn": nextInsectIn(g), "catchCooldown": domain.Clamp(int(catchWait.Seconds())-secs(g.Life.LastCatch, g.Now), 0, int(catchWait.Seconds()))}, "careTimers": map[string]int{"farmerHunger": domain.FarmerHungerCap, "animalHunger": domain.AnimalHungerCap, "cropWater": domain.CropWaterCap}, "entities": g.Entities, "wildInsects": g.Insects, "inventory": g.Inventory, "catalog": domain.Goods, "labels": domain.Labels, "sellPrices": domain.SellPrices, "shopSupplies": domain.ShopSupplies, "history": history, "grid": map[string]int{"width": domain.Width, "height": domain.Height}, "serverTime": g.Now}
			return nil
		})
		if e != nil {
			return e
		}
		write(w, 200, state)
		return nil
	})
	s.route("POST", "/api/game/place", []string{"PLAYER"}, func(w http.ResponseWriter, r *http.Request, u User) error {
		var v dto.PlaceRequest
		if e := decode(r, &v); e != nil {
			return e
		}
		good, ok := domain.Goods[v.Kind]
		if !ok {
			return bad(400, "Vật phẩm không có trong cửa hàng")
		}
		if !goodTile(v.X, v.Y, v.Kind) {
			return bad(400, "Ô này không dùng để xây/trồng được")
		}
		e := s.withGame(r, u, func(tx pgx.Tx, g *gameTx) error {
			if e := activeWorker(g); e != nil {
				return e
			}
			if g.intersects(v.X, v.Y, v.Kind, "") {
				return bad(409, "Vật phẩm bị chồng lên công trình khác")
			}
			if good.Category == "ANIMAL" && domain.HasHousing(v.Kind) {
				ok, _ := g.nearestHousing(v.Kind, v.X, v.Y)
				if !ok {
					if (v.Kind == "fish" || v.Kind == "frog") && g.waterHomeAt(v.X, v.Y) != nil {
						h := g.waterHomeAt(v.X, v.Y)
						if h.BuildLeft > 0 {
							return bad(409, "Ao/thùng đang xây, hãy chờ hoàn thành trước khi thả vật nuôi")
						}
						if h.RT.Oxygen <= domain.OxygenMinimum {
							return bad(409, "Ao/thùng chỉ còn %d%% oxy. Hãy bơm oxy trước khi thả thêm vật nuôi", h.RT.Oxygen)
						}
						return bad(409, "Ao/thùng đã đầy, hãy chọn nơi nuôi khác")
					}
					return bad(409, "Hãy xây %s và chờ hoàn thành trước khi nuôi %s", func() string {
						if v.Kind == "bee" {
							return "tổ ong"
						}
						return "ao hoặc thùng"
					}(), good.Label)
				}
			}
			if e := s.gameCoins(r, tx, g, -good.Price, 4, "BUY", v.Kind, 1); e != nil {
				return e
			}
			id := newID()
			_, e := tx.Exec(r.Context(), `INSERT INTO world_entities(id,farm_id,category,kind,x,y) VALUES($1,$2,$3,$4,$5,$6)`, id, g.Farm.ID, good.Category, v.Kind, v.X, v.Y)
			if e != nil {
				return e
			}
			var until *time.Time
			if good.Category == "STRUCTURE" {
				done := g.Now.Add(time.Duration(good.Seconds) * time.Second)
				until = &done
			}
			initialHunger := domain.AnimalHungerCap
			if good.Category != "ANIMAL" {
				initialHunger = 0
			}
			_, e = tx.Exec(r.Context(), `INSERT INTO entity_runtime(entity_id,last_tick,hunger_seconds,build_until) VALUES($1,$2,$3,$4)`, id, g.Now, initialHunger, until)
			if e != nil {
				return e
			}
			return s.evictWildInsects(r, tx, g, v.X, v.Y, v.Kind)
		})
		if e != nil {
			return e
		}
		success(w, "Đã thêm "+good.Label+" vào nông trại!")
		return nil
	})
	// Safe removal: server controls refunds, and never deletes a habitat with
	// occupants or an asset reserved for a real-world connection.
	s.route("POST", "/api/game/remove", []string{"PLAYER"}, func(w http.ResponseWriter, r *http.Request, u User) error {
		var v dto.EntityRequest
		if e := decode(r, &v); e != nil {
			return e
		}
		if !validUUID(v.EntityID) {
			return bad(400, "Mã vật phẩm không hợp lệ")
		}
		refund := 0
		err := s.withGame(r, u, func(tx pgx.Tx, g *gameTx) error {
			if e := activeWorker(g); e != nil {
				return e
			}
			o := g.entity(v.EntityID)
			if o == nil {
				return bad(404, "Không tìm thấy vật phẩm")
			}
			if e := checkReservedAnimal(r, tx, o); e != nil {
				return e
			}
			if o.Kind == "pond" || o.Kind == "tank" || o.Kind == "aquaponics" || o.Kind == "hive" {
				width, height := domain.Footprint(o.Kind)
				for _, child := range g.Entities {
					if child.ID == o.ID {
						continue
					}
					if (o.Kind == "pond" || o.Kind == "tank") && (child.Kind == "fish" || child.Kind == "frog") &&
						child.X >= o.X && child.X < o.X+width && child.Y >= o.Y && child.Y < o.Y+height {
						return bad(409, "Di chuyển hoặc thu hoạch cá/ếch trước khi dỡ nơi nuôi")
					}
					if o.Kind == "aquaponics" && child.Category == "CROP" &&
						child.X >= o.X && child.X < o.X+width && child.Y >= o.Y && child.Y < o.Y+height {
						return bad(409, "Hãy dời hoặc gỡ cây trên giàn trước khi tháo giàn aquaponics")
					}
					if o.Kind == "hive" && child.Kind == "bee" && near(o.X, o.Y, child.X, child.Y, 2) {
						return bad(409, "Hãy chuyển ong sang tổ khác trước khi dỡ tổ")
					}
				}
			}
			age := secs(o.CreatedAt, g.Now)
			refund = domain.RemovalRefund(o.Kind, age)
			xpReversal := 0
			if age < 30 {
				xpReversal = -min(4, g.Farm.XP)
			} // BUY grants 4 XP; undo free-placement XP too.
			if refund > 0 || xpReversal < 0 {
				if e := s.gameCoins(r, tx, g, refund, xpReversal, "REMOVE_REFUND", o.Kind, 1); e != nil {
					return e
				}
			}
			_, e := tx.Exec(r.Context(), `DELETE FROM world_entities WHERE id=$1 AND farm_id=$2`, o.ID, g.Farm.ID)
			if e != nil {
				return e
			}
			return nil
		})
		if err != nil {
			return err
		}
		success(w, fmt.Sprintf("Đã dỡ vật thể khỏi nông trại. Hoàn %d Xu Lá.", refund))
		return nil
	})
	s.route("POST", "/api/game/move", []string{"PLAYER"}, func(w http.ResponseWriter, r *http.Request, u User) error {
		var v dto.MoveRequest
		if e := decode(r, &v); e != nil {
			return e
		}
		if !validUUID(v.EntityID) {
			return bad(400, "Mã vật phẩm không đúng")
		}
		e := s.withGame(r, u, func(tx pgx.Tx, g *gameTx) error {
			if e := activeWorker(g); e != nil {
				return e
			}
			o := g.entity(v.EntityID)
			if o == nil {
				return bad(404, "Không tìm thấy vật phẩm")
			}
			if e := checkReservedAnimal(r, tx, o); e != nil {
				return e
			}
			if !goodTile(v.X, v.Y, o.Kind) || g.intersects(v.X, v.Y, o.Kind, o.ID) {
				return bad(409, "Vị trí không hợp lệ hoặc bị chồng lên")
			}
			// Keep fish/frog and bees within their housing radius when moved.
			if domain.HasHousing(o.Kind) {
				// Moving inside a full habitat is permitted: the existing animal
				// already occupies a slot, and must not be counted twice.
				prevX, prevY := o.X, o.Y
				o.X, o.Y = v.X, v.Y
				ok, _ := g.nearestHousing(o.Kind, v.X, v.Y)
				o.X, o.Y = prevX, prevY
				if !ok {
					return bad(409, "Hãy chọn một ô còn trống trong ao/thùng hoặc cạnh tổ ong")
				}
			}
			if o.Kind == "pond" || o.Kind == "tank" || o.Kind == "hive" || o.Kind == "aquaponics" {
				w, h := domain.Footprint(o.Kind)
				for _, a := range g.Entities {
					if a.Category != "ANIMAL" && !(o.Kind == "aquaponics" && a.Category == "CROP") {
						continue
					}
					if (o.Kind == "pond" || o.Kind == "tank") && (a.Kind == "fish" || a.Kind == "frog") && a.X >= o.X && a.X < o.X+w && a.Y >= o.Y && a.Y < o.Y+h {
						return bad(409, "Cần di chuyển vật nuôi ra trước khi dời công trình")
					}
					if o.Kind == "aquaponics" && a.Category == "CROP" && a.X >= o.X && a.X < o.X+w && a.Y >= o.Y && a.Y < o.Y+h {
						return bad(409, "Cần dời cây khỏi giàn trước khi chuyển giàn")
					}
					if o.Kind == "hive" && a.Kind == "bee" && near(o.X, o.Y, a.X, a.Y, 2) {
						return bad(409, "Cần di chuyển ong ra trước khi dời tổ")
					}
				}
			}
			_, e := tx.Exec(r.Context(), `UPDATE world_entities SET x=$2,y=$3 WHERE id=$1`, v.EntityID, v.X, v.Y)
			if e != nil {
				return e
			}
			return s.evictWildInsects(r, tx, g, v.X, v.Y, o.Kind)
		})
		if e != nil {
			return e
		}
		success(w, "Đã chuyển vật phẩm")
		return nil
	})
	s.route("POST", "/api/game/shop", []string{"PLAYER"}, func(w http.ResponseWriter, r *http.Request, u User) error {
		var v dto.ItemQuantityRequest
		if e := decode(r, &v); e != nil {
			return e
		}
		price, ok := domain.ShopSupplies[v.Kind]
		if !ok || v.Quantity < 1 || v.Quantity > 20 {
			return bad(400, "Vật phẩm/ số lượng không hợp lệ")
		}
		e := s.withGame(r, u, func(tx pgx.Tx, g *gameTx) error {
			// Purchasing rice is an emergency escape hatch when the farmer is hungry.
			// Other shopping requires a farmer fit to work.
			if v.Kind != "rice" {
				if e := activeWorker(g); e != nil {
					return e
				}
			}
			if e := s.gameCoins(r, tx, g, -price*v.Quantity, 0, "SUPPLY", v.Kind, v.Quantity); e != nil {
				return e
			}
			return s.gameInv(r, tx, g, v.Kind, v.Quantity)
		})
		if e != nil {
			return e
		}
		success(w, "Đã mua và đưa vật phẩm vào kho")
		return nil
	})
	s.route("POST", "/api/game/sell", []string{"PLAYER"}, func(w http.ResponseWriter, r *http.Request, u User) error {
		var v dto.ItemQuantityRequest
		if e := decode(r, &v); e != nil {
			return e
		}
		price, ok := domain.SellPrices[v.Kind]
		if !ok || v.Quantity < 1 || v.Quantity > 100 {
			return bad(400, "Không thể bán mặt hàng này")
		}
		e := s.withGame(r, u, func(tx pgx.Tx, g *gameTx) error {
			if e := activeWorker(g); e != nil {
				return e
			}
			if e := s.gameInv(r, tx, g, v.Kind, -v.Quantity); e != nil {
				return e
			}
			return s.gameCoins(r, tx, g, price*v.Quantity, v.Quantity*3, "SELL_TO_RESTAURANT", v.Kind, v.Quantity)
		})
		if e != nil {
			return e
		}
		success(w, fmt.Sprintf("Nhà hàng đã mua %d %s (+%d Xu Lá)", v.Quantity, domain.Labels[v.Kind], price*v.Quantity))
		return nil
	})
	s.route("POST", "/api/game/craft", []string{"PLAYER"}, func(w http.ResponseWriter, r *http.Request, u User) error {
		var v dto.CraftRequest
		if e := decode(r, &v); e != nil {
			return e
		}
		if (v.Recipe != "mill_rice" && v.Recipe != "cook_meal") || v.Quantity < 1 || v.Quantity > 20 {
			return bad(400, "Công thức hoặc số lượng không hợp lệ")
		}
		message := "Đã chế biến"
		e := s.withGame(r, u, func(tx pgx.Tx, g *gameTx) error {
			switch v.Recipe {
			case "mill_rice":
				// Milling is also allowed when hungry: otherwise a farmer with paddy,
				// zero rice and zero coins would be permanently soft-locked.
				if e := s.gameInv(r, tx, g, "paddy", -2*v.Quantity); e != nil {
					return e
				}
				if e := s.gameInv(r, tx, g, "rice", v.Quantity); e != nil {
					return e
				}
				message = fmt.Sprintf("Đã xay %d thóc thành %d gạo", 2*v.Quantity, v.Quantity)
				return s.gameCoins(r, tx, g, 0, 5*v.Quantity, "MILL_RICE", "rice", v.Quantity)
			case "cook_meal":
				// A cooked meal MUST consume rice. Old meals remain valid for backwards
				// compatibility, but uncooked rice/vegetables never directly restore energy.
				ordinary := min(g.Inventory["rice"], v.Quantity)
				aid := v.Quantity - ordinary
				if g.Inventory["aid_rice"] < aid {
					return bad(409, "Cần %d gạo để nấu %d phần cơm", v.Quantity, v.Quantity)
				}
				if ordinary > 0 {
					if e := s.gameInv(r, tx, g, "rice", -ordinary); e != nil {
						return e
					}
				}
				if aid > 0 {
					if e := s.gameInv(r, tx, g, "aid_rice", -aid); e != nil {
						return e
					}
				}
				if e := s.gameInv(r, tx, g, "meal", v.Quantity); e != nil {
					return e
				}
				message = fmt.Sprintf("Đã nấu %d phần cơm, sẵn sàng cho nông dân ăn!", v.Quantity)
				return s.gameCoins(r, tx, g, 0, 3*v.Quantity, "COOK_MEAL", "meal", v.Quantity)
			}
			return bad(400, "Công thức không tồn tại")
		})
		if e != nil {
			return e
		}
		success(w, message)
		return nil
	})
	s.route("POST", "/api/game/aid", []string{"PLAYER"}, func(w http.ResponseWriter, r *http.Request, u User) error {
		e := s.withGame(r, u, func(tx pgx.Tx, g *gameTx) error {
			if !domain.CanReceiveEmergencyRice(g.Farm.Coins, g.Life.Hunger, g.Inventory) {
				return bad(409, "Chỉ nhận gạo cứu trợ khi đang đói, hết thức ăn và không đủ xu mua gạo")
			}
			// Aid rice cannot be sold, fed to animals or milled into trade goods.
			if e := s.gameInv(r, tx, g, "aid_rice", 1); e != nil {
				return e
			}
			return s.gameCoins(r, tx, g, 0, 0, "EMERGENCY_RICE", "aid_rice", 1)
		})
		if e != nil {
			return e
		}
		success(w, "Bếp cộng đồng tặng bạn 1 gạo. Hãy nấu cơm rồi ăn để tiếp tục!")
		return nil
	})
	s.route("POST", "/api/game/catch", []string{"PLAYER"}, func(w http.ResponseWriter, r *http.Request, u User) error {
		var request dto.CatchRequest
		if e := decode(r, &request); e != nil {
			return e
		}
		if !validUUID(request.InsectID) {
			return bad(400, "Hãy nhấn vào một côn trùng trên bản đồ")
		}
		captured := ""
		e := s.withGame(r, u, func(tx pgx.Tx, g *gameTx) error {
			if e := activeWorker(g); e != nil {
				return e
			}
			if g.Now.Sub(g.Life.LastCatch) < catchWait {
				return bad(429, "Bạn hãy chờ vài giây trước khi bắt tiếp")
			}
			for _, bug := range g.Insects {
				if bug.ID == request.InsectID {
					captured = bug.Species
					break
				}
			}
			if captured == "" {
				return bad(409, "Côn trùng đã bay mất. Hãy chọn con khác!")
			}
			tag, e := tx.Exec(r.Context(), `DELETE FROM farm_wild_insects WHERE farm_id=$1 AND id=$2 AND expires_at > $3`, g.Farm.ID, request.InsectID, g.Now)
			if e != nil {
				return e
			}
			if tag.RowsAffected() != 1 {
				return bad(409, "Côn trùng đã bay mất. Hãy chọn con khác!")
			}
			g.Life.LastCatch = g.Now
			g.Life.Insects--
			if _, e = tx.Exec(r.Context(), `UPDATE farm_economy SET insects=$2,last_catch=$3 WHERE farm_id=$1`, g.Farm.ID, g.Life.Insects, g.Life.LastCatch); e != nil {
				return e
			}
			if e = s.gameInv(r, tx, g, "insect", 1); e != nil {
				return e
			}
			return s.gameCoins(r, tx, g, 0, 8, "CATCH", captured, 1)
		})
		if e != nil {
			return e
		}
		success(w, "Bắt được "+wildNames[captured]+"! +1 côn trùng cho ếch ăn")
		return nil
	})
	s.route("POST", "/api/game/eat", []string{"PLAYER"}, func(w http.ResponseWriter, r *http.Request, u User) error {
		e := s.withGame(r, u, func(tx pgx.Tx, g *gameTx) error {
			if g.Life.Hunger > domain.FarmerHungerCap*3/4 {
				return bad(409, "Nông dân vẫn còn no, hãy để dành cơm nhé!")
			}
			if g.Inventory["meal"] < 1 {
				return bad(409, "Nông dân cần ăn cơm! Hãy xay thóc lấy gạo, nấu cơm rồi ăn.")
			}
			if e := s.gameInv(r, tx, g, "meal", -1); e != nil {
				return e
			}
			g.Life.Hunger = domain.FarmerHungerCap
			if _, e := tx.Exec(r.Context(), `UPDATE farm_economy SET hunger_seconds=$2,last_tick=$3 WHERE farm_id=$1`, g.Farm.ID, g.Life.Hunger, g.Now); e != nil {
				return e
			}
			return s.gameCoins(r, tx, g, 0, 0, "EAT_MEAL", "meal", 1)
		})
		if e != nil {
			return e
		}
		success(w, "Nông dân đã ăn cơm và hồi đầy năng lượng! Có thể tiếp tục làm việc.")
		return nil
	})
	s.route("POST", "/api/game/action", []string{"PLAYER"}, func(w http.ResponseWriter, r *http.Request, u User) error {
		var v dto.ActionRequest
		if e := decode(r, &v); e != nil {
			return e
		}
		if !validUUID(v.EntityID) {
			return bad(400, "Mã vật phẩm không hợp lệ")
		}
		message := "Đã thực hiện hành động"
		var learning *farm.Result
		e := s.withGame(r, u, func(tx pgx.Tx, g *gameTx) error {
			if e := activeWorker(g); e != nil {
				return e
			}
			if v.Action == "HARVEST" || v.Action == "SELL_CHICKEN" {
				result, replay, err := s.gradeHarvest(r, tx, g, u, v.EntityID, v.Action, v.ChallengeID, v.Answer)
				if err != nil {
					return err
				}
				learning = &result
				if replay || !result.Correct {
					return nil
				}
			}
			o := g.entity(v.EntityID)
			if o == nil {
				return bad(404, "Không tìm thấy vật phẩm")
			}
			switch v.Action {
			case "WATER":
				if o.Category != "CROP" {
					return bad(409, "Chỉ tưới được cây trồng")
				}
				if o.RT.Ready > 0 {
					return bad(409, "Cây đã thu hoạch được rồi")
				}
				if !domain.CanWaterCrop(o.RT, g.Now) {
					return bad(409, "Cây vừa thu hoạch, chờ %d giây rồi tưới lại nhé!", domain.CropRegrowLeft(o.RT, g.Now))
				}
				if g.aquaFor(o.X, o.Y) != nil {
					return bad(409, "Cây trên giàn aquaponics tự lấy nước. Hãy bổ sung oxy cho giàn nếu cần.")
				}
				if o.RT.Water > domain.CropWaterCap*2/3 {
					return bad(409, "Đất vẫn đủ ẩm")
				}
				isRegrowing := o.RT.RegrowUntil != nil
				o.RT = domain.WaterCrop(o.RT, g.Now)
				if isRegrowing {
					message = "Đã tưới lại! Cây bắt đầu vụ mới ngay trên luống cũ."
				} else {
					message = "Đã tưới nước. Cây phát triển khi đủ ẩm."
				}
			case "FEED":
				if o.Category != "ANIMAL" {
					return bad(409, "Chỉ động vật mới cần cho ăn")
				}

				if o.RT.Hunger > domain.AnimalHungerCap/3 {
					return bad(409, "Vật nuôi còn no, không cần cho ăn thêm")
				}
				if domain.HasHousing(o.Kind) && !o.Housed {
					if (o.Kind == "frog" || o.Kind == "fish") && o.HabitatBuildLeft > 0 {
						return bad(409, "Ao/thùng chưa xây xong. Hãy chờ hoàn thành để cho vật nuôi ăn")
					}
					return bad(409, "Vật nuôi chưa nằm trong ao/thùng đã xây xong (hoặc ong chưa có tổ). Hãy di chuyển đến nơi ở phù hợp")
				}
				var food string
				switch o.Kind {
				case "chicken":
					food = "paddy"
				case "frog":
					for _, k := range []string{"insect", "frog_feed"} {
						if g.Inventory[k] > 0 {
							food = k
							break
						}
					}
				case "fish":
					for _, k := range []string{"water_spinach", "fish_feed"} {
						if g.Inventory[k] > 0 {
							food = k
							break
						}
					}
				case "bee":
					if !g.flowerNear(o.X, o.Y) {
						return bad(409, "Cần trồng hoa đã nở gần tổ ong")
					}
					food = "nectar"
				}
				// A user may choose a particular feed from the inventory. Never
				// allow arbitrary goods to be consumed by a different species.
				if v.Item != "" {
					valid := map[string][]string{
						"chicken": {"paddy"}, "frog": {"insect", "frog_feed"},
						"fish": {"water_spinach", "fish_feed"}, "bee": {"nectar"},
					}
					allowed := false
					for _, k := range valid[o.Kind] {
						if k == v.Item {
							allowed = true
							break
						}
					}
					if !allowed {
						return bad(409, "Thức ăn không phù hợp với vật nuôi")
					}
					food = v.Item
				}
				if food == "" {
					return bad(409, "Không có thức ăn phù hợp trong kho")
				}
				if food != "nectar" && g.Inventory[food] <= 0 {
					return bad(409, "Kho đã hết %s", domain.Labels[food])
				}
				if food != "nectar" {
					if e := s.gameInv(r, tx, g, food, -1); e != nil {
						return e
					}
				}
				o.RT.Hunger = domain.AnimalHungerCap
				o.RT.Starvation = 0
				if (o.Kind == "frog" || o.Kind == "fish") && !o.HasOxygen {
					message = "Đã cho ăn! Tuy nhiên ao/thùng thiếu oxy nên vật nuôi tạm ngừng lớn. Hãy bơm oxy cho nơi nuôi."
				} else {
					message = "Đã cho ăn. Đồng hồ sản xuất tiếp tục chạy khi vật nuôi khỏe."
				}
			case "MEDICINE":
				if o.Category != "ANIMAL" || !o.RT.Sick {
					return bad(409, "Vật nuôi chưa cần chữa bệnh")
				}
				if e := s.gameInv(r, tx, g, "medicine", -1); e != nil {
					return e
				}
				o.RT.Health = 90
				o.RT.Sick = false
				message = "Đã chăm sóc thú y và phục hồi sức khỏe"
			case "OXYGEN":
				if domain.OxygenThresholdSeconds(o.Kind) == 0 {
					return bad(409, "Oxy chỉ dùng cho thùng, ao và giàn aquaponics")
				}
				if o.RT.Oxygen > 65 {
					return bad(409, "Oxy đang đủ, nên để dành bình!")
				}
				if e := s.gameInv(r, tx, g, "oxygen", -1); e != nil {
					return e
				}
				o.RT = domain.RefillOxygen(o.RT)
				message = "Đã bổ sung oxy cho nguồn nước"
			case "HARVEST":
				if o.Category != "CROP" && o.Category != "ANIMAL" {
					return bad(409, "Không thể thu hoạch")
				}
				if o.RT.Ready == 0 {
					return bad(409, "Chưa tới lúc thu hoạch; xem thanh tiến độ")
				}
				if (o.Kind == "frog" || o.Kind == "fish") && (o.RT.Hunger == 0 || o.RT.Sick || !o.Housed || !o.HasOxygen) {
					return bad(409, "Cá/ếch cần no, khỏe, ở trong ao/thùng đã xây xong và có oxy trên 15%% trước khi xuất bán")
				}
				if o.Kind == "chicken" || o.Kind == "bee" {
					o.RT.Ready--
					if e := s.gameInv(r, tx, g, domain.Goods[o.Kind].Yield, 1); e != nil {
						return e
					}
					message = "Đã đưa sản phẩm vào kho (vật nuôi vẫn còn)"
				} else if o.Category == "CROP" {
					if e := s.gameInv(r, tx, g, domain.Goods[o.Kind].Yield, domain.Goods[o.Kind].Amount); e != nil {
						return e
					}
					// Leave world_entities untouched: same plot, same plant and same ID.
					// State is persisted in entity_runtime, including cooldown across reloads.
					o.RT = domain.HarvestCrop(o.RT, g.Now)
					if g.aquaFor(o.X, o.Y) != nil {
						message = "Đã thu hoạch! Cây trên giàn tự mọc lại sau 40 giây nếu còn oxy."
					} else {
						message = "Đã thu hoạch! Chờ 40 giây rồi tưới lại để cây lớn tiếp."
					}
				} else {
					if e := checkReservedAnimal(r, tx, o); e != nil {
						return e
					}
					if e := s.gameInv(r, tx, g, domain.Goods[o.Kind].Yield, domain.Goods[o.Kind].Amount); e != nil {
						return e
					}
					_, e := tx.Exec(r.Context(), `DELETE FROM world_entities WHERE id=$1`, o.ID)
					if e != nil {
						return e
					}
					message = "Thu hoạch xong! Sản phẩm đã vào kho. Có thể bán cho nhà hàng."
				}
			case "SELL_CHICKEN":
				if o.Kind != "chicken" || o.Linked {
					return bad(409, "Chỉ được bán gà ảo không liên kết")
				}
				// A grown chicken must have completed at least one laying cycle; avoid instant flipping.
				if e := checkReservedAnimal(r, tx, o); e != nil {
					return e
				}
				if o.RT.Hunger == 0 || o.RT.Sick || o.RT.Health < 65 {
					return bad(409, "Cần chăm gà khỏe và cho ăn trước khi xuất bán")
				}
				if secs(o.CreatedAt, g.Now) < 420 {
					return bad(409, "Gà chưa tới tuổi bán, hãy chăm đến kỳ đẻ đầu tiên")
				}
				if e := s.gameInv(r, tx, g, "chicken_product", 1); e != nil {
					return e
				}
				_, e := tx.Exec(r.Context(), `DELETE FROM world_entities WHERE id=$1`, o.ID)
				if e != nil {
					return e
				}
				message = "Gà đã vào kho thương phẩm, có thể bán cho nhà hàng."
			default:
				return bad(400, "Hành động chưa được hỗ trợ")
			}
			// Only harvested fish/frog and sold chickens are removed. Crops retain
			// their row and must persist the freshly reset growth/cooldown state.
			if v.Action != "SELL_CHICKEN" && (v.Action != "HARVEST" || o.Category == "CROP" || o.Kind == "chicken" || o.Kind == "bee") {
				if e := updateRuntime(r, tx, o); e != nil {
					return e
				}
			}
			return s.gameCoins(r, tx, g, 0, 6, "ACTION_"+v.Action, o.Kind, 1)
		})
		if e != nil {
			return e
		}
		if learning != nil {
			write(w, 200, learning)
		} else {
			success(w, message)
		}
		return nil
	})
	s.route("POST", "/api/game/rename", []string{"PLAYER"}, func(w http.ResponseWriter, r *http.Request, u User) error {
		var v dto.RenameRequest
		if e := decode(r, &v); e != nil {
			return e
		}
		v.Name = clean(v.Name, 90)
		if len([]rune(v.Name)) < 3 {
			return bad(400, "Tên nông trại cần ít nhất 3 ký tự")
		}
		_, e := s.DB.Exec(r.Context(), `UPDATE virtual_farms SET name=$2 WHERE owner_id=$1`, u.ID, v.Name)
		if e != nil {
			return e
		}
		success(w, "Đã đổi tên khu vườn")
		return nil
	})
}
